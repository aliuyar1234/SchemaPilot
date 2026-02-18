from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from backend.control_plane.repository import create_run, create_source, create_workspace, get_run
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import Base, GovernancePolicy, ReviewTask
from backend.workers.run_processor import process_run_by_id
from backend.workers.semantic_drift import detect_semantic_manifest_drift


def test_detect_semantic_manifest_drift_flags_missing_columns() -> None:
    manifest = {
        "entities": [{"entity_id": "invoice", "dataset_id": "dataset-1"}],
        "dimensions": [{"dimension_id": "region", "entity_id": "invoice"}],
        "metrics": [
            {"metric_id": "invoice_amount_sum", "entity_id": "invoice", "expression": "sum(amount)"}
        ],
    }
    drift = detect_semantic_manifest_drift(
        semantic_manifest=manifest,
        available_columns_by_dataset={"dataset-1": {"amount"}},
    )
    assert drift["drift_detected"] is True
    assert drift["issue_count"] >= 1


def test_discover_run_creates_semantic_drift_blocking_task(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'semantic_drift.db').as_posix()}"
    storage_root = (tmp_path / "storage").as_posix()
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "invoices.csv").write_text("id,amount\n1,10\n", encoding="utf-8")

    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Semantic Drift Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        create_source(
            session,
            workspace_id=workspace_id,
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Exports",
        )
        session.add(
            GovernancePolicy(
                policy_id=new_ulid(),
                workspace_id=workspace_id,
                policy_type="semantic_manifest",
                definition_ref=json.dumps(
                    {
                        "semantic_manifest": {
                            "workspace_id": workspace_id,
                            "manifest_version": "1.0.0",
                            "entities": [{"entity_id": "invoice", "dataset_id": "dataset-1"}],
                            "dimensions": [{"dimension_id": "region", "entity_id": "invoice"}],
                            "metrics": [
                                {
                                    "metric_id": "invoice_amount_sum",
                                    "entity_id": "invoice",
                                    "expression": "sum(amount)",
                                }
                            ],
                            "joins": [],
                        }
                    },
                    sort_keys=True,
                ),
                status="active",
            )
        )
        run = create_run(session, workspace_id=workspace_id, run_type="discover")
        session.commit()
        run_id = str(run["run_id"])

    with session_factory() as session:
        processed = process_run_by_id(
            session,
            run_id=run_id,
            storage_root=storage_root,
            strict_ingest=False,
        )
        session.commit()
    assert processed is not None
    assert processed.status == "succeeded"
    assert processed.output_refs["semantic_drift_blocking_tasks_created"] == 1

    with session_factory() as session:
        run_state = get_run(session, workspace_id=workspace_id, run_id=run_id)
        assert run_state is not None
        tasks = (
            session.execute(select(ReviewTask).where(ReviewTask.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        assert any(task.priority == "quality_critical" and task.blocking for task in tasks)
