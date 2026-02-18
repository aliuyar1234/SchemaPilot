from __future__ import annotations

from pathlib import Path

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import Base, ReviewTask, RunRecord
from tools.kpi_extract import extract_kpis


def test_kpi_extract_derives_runtime_metrics_from_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'kpi_extract.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        session.add(
            AuditEvent(
                audit_event_id=new_ulid(),
                workspace_id="w1",
                actor_id="user:admin",
                event_type="workspace.created",
                event_json={"workspace_id": "w1"},
                correlation_id=new_ulid(),
            )
        )
        session.add(
            AuditEvent(
                audit_event_id=new_ulid(),
                workspace_id="w1",
                actor_id="user:steward",
                event_type="build.published",
                event_json={"status": "published"},
                correlation_id=new_ulid(),
            )
        )
        session.add(
            AccessDecision(
                decision_id=new_ulid(),
                workspace_id="w1",
                actor_id="user:analyst",
                request_context_json={"endpoint": "query"},
                resources_json={"endpoint": "query"},
                result="allow",
                applied_filters_json={},
                applied_masks_json={},
                audit_event_id=new_ulid(),
            )
        )
        session.add(
            AccessDecision(
                decision_id=new_ulid(),
                workspace_id="w1",
                actor_id="user:analyst",
                request_context_json={"endpoint": "query"},
                resources_json={"endpoint": "query"},
                result="deny",
                applied_filters_json={},
                applied_masks_json={},
                audit_event_id=new_ulid(),
            )
        )
        session.add(
            RunRecord(
                run_id=new_ulid(),
                workspace_id="w1",
                run_type="discover",
                status="succeeded",
                input_refs_json={"source_ids": ["s1"]},
                output_refs_json={"dataset_ids": ["d1"]},
            )
        )
        session.add(
            RunRecord(
                run_id=new_ulid(),
                workspace_id="w1",
                run_type="discover",
                status="succeeded",
                input_refs_json={"source_ids": ["s1"]},
                output_refs_json={"dataset_ids": ["d1"]},
            )
        )
        session.add(
            RunRecord(
                run_id=new_ulid(),
                workspace_id="w1",
                run_type="discover",
                status="failed",
                input_refs_json={"source_ids": ["s2"]},
                output_refs_json={"dataset_ids": []},
            )
        )
        session.add(
            ReviewTask(
                task_id=new_ulid(),
                workspace_id="w1",
                priority="quality_critical",
                subject_ref="proposal-1",
                status="open",
                blocking=True,
            )
        )
        session.commit()

    with session_factory() as session:
        metrics = extract_kpis(session)

    assert metrics["run_success_rate"] == 2 / 3
    assert metrics["policy_denial_count"] == 1
    assert metrics["published_build_count"] == 1
    assert metrics["review_queue_blocking_open_tasks"] == 1
    assert metrics["deterministic_rebuild_pass_rate"] == 1.0
    assert metrics["time_to_first_safe_answer_minutes"] is not None
