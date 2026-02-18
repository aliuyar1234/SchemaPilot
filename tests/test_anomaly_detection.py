from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from backend.control_plane.repository import create_run, create_source, create_workspace
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base, ReviewProposal, ReviewTask, RunRecord
from backend.workers.anomaly_detection import detect_profile_anomalies
from backend.workers.run_processor import process_run_by_id


def test_detect_profile_anomalies_flags_parse_and_null_issues() -> None:
    anomalies = detect_profile_anomalies(
        {
            "parse_error_rate": 0.2,
            "null_rates": {"email": 0.8},
            "unique_ratio": {"status": 0.005},
        }
    )
    anomaly_types = {str(item["type"]) for item in anomalies}
    assert "parse_error_spike" in anomaly_types
    assert "high_null_rate" in anomaly_types
    assert "low_uniqueness" in anomaly_types


def test_discover_run_creates_anomaly_blocking_task(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'anomaly.db').as_posix()}"
    storage_root = tmp_path / "storage"
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    # High null-rate column should trigger anomaly proposal/task.
    (exports_root / "records.csv").write_text(
        "id,email\n1,\n2,\n3,\n4,a@example.com\n", encoding="utf-8"
    )

    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Anomaly Workspace",
            profile="starter",
            security_baseline="standard",
        )
        workspace_id = str(workspace["workspace_id"])
        create_source(
            session,
            workspace_id=workspace_id,
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix()},
            display_name="exports",
        )
        run_payload = create_run(session, workspace_id=workspace_id, run_type="discover")
        run_id = str(run_payload["run_id"])
        session.commit()

    with session_factory() as session:
        processed = process_run_by_id(
            session,
            run_id=run_id,
            storage_root=storage_root.as_posix(),
            strict_ingest=True,
        )
        assert processed is not None
        session.commit()

    with session_factory() as session:
        run_record = session.get(RunRecord, run_id)
        assert run_record is not None
        output_refs = run_record.output_refs_json
        assert int(output_refs.get("anomaly_blocking_tasks_created", 0)) == 1
        proposal = (
            session.execute(
                select(ReviewProposal).where(
                    ReviewProposal.workspace_id == workspace_id,
                    ReviewProposal.proposal_type == "anomaly_detection_proposal",
                )
            )
            .scalars()
            .first()
        )
        assert proposal is not None
        task = (
            session.execute(
                select(ReviewTask).where(
                    ReviewTask.workspace_id == workspace_id,
                    ReviewTask.subject_ref == proposal.proposal_id,
                    ReviewTask.blocking.is_(True),
                )
            )
            .scalars()
            .first()
        )
        assert task is not None
        assert task.priority == "quality_critical"
