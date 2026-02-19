from __future__ import annotations

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    Base,
    CatalogDataset,
    CatalogSource,
    ReviewTask,
    RunRecord,
    TargetDbState,
    TargetDbSyncCursor,
    Workspace,
)
from cli.schemapilot_cli.slo import export_slo_snapshot, render_slo_csv


def _seed(database_url: str, *, workspace_id: str) -> None:
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        session.add(
            Workspace(
                workspace_id=workspace_id,
                name="SLO Workspace",
                profile="team",
                security_baseline="strict",
            )
        )
        session.add(
            CatalogSource(
                source_id="src-1",
                workspace_id=workspace_id,
                source_type="filesystem",
                scope_json={"root_path": "/tmp"},
                credentials_ref=None,
                status="active",
                display_name="Export Files",
            )
        )
        session.add(
            CatalogDataset(
                dataset_id="ds-1",
                workspace_id=workspace_id,
                source_id="src-1",
                logical_name="orders",
                physical_locator="orders.csv",
                schema_version=1,
                sensitivity_summary_json={"classification": "internal"},
            )
        )
        discover_run_id = new_ulid()
        session.add(
            RunRecord(
                run_id=discover_run_id,
                workspace_id=workspace_id,
                run_type="discover",
                status="succeeded",
                input_refs_json={},
                output_refs_json={},
            )
        )
        session.add(
            RunRecord(
                run_id=new_ulid(),
                workspace_id=workspace_id,
                run_type="discover",
                status="queued",
                input_refs_json={},
                output_refs_json={},
            )
        )
        session.add(
            ReviewTask(
                task_id=new_ulid(),
                workspace_id=workspace_id,
                priority="quality_critical",
                subject_ref="proposal-1",
                status="open",
                blocking=True,
            )
        )
        audit_event_id = new_ulid()
        session.add(
            AuditEvent(
                audit_event_id=audit_event_id,
                workspace_id=workspace_id,
                actor_id="actor:ai",
                event_type="gateway.query",
                event_json={"reason": "dataset_not_allowed"},
                correlation_id=new_ulid(),
            )
        )
        session.add(
            AccessDecision(
                decision_id=new_ulid(),
                workspace_id=workspace_id,
                actor_id="actor:ai",
                request_context_json={"workspace_id": workspace_id},
                resources_json={"endpoint": "query"},
                result="deny",
                applied_filters_json={},
                applied_masks_json={},
                audit_event_id=audit_event_id,
            )
        )
        session.add(
            TargetDbState(
                workspace_id=workspace_id,
                active_target_db_id="tdb-1",
                current_build_id="build-1",
                current_schema_ref="schema-v1",
                last_successful_sync_epoch=1,
                health_status="healthy",
                last_validation_run_id=None,
                last_error_evidence_bundle_uri=None,
                sync_status_json={"datasets": ["ds-1"]},
            )
        )
        session.add(
            TargetDbSyncCursor(
                sync_cursor_id=new_ulid(),
                workspace_id=workspace_id,
                target_db_id="tdb-1",
                dataset_id="ds-1",
                cursor_hash="abc123",
                last_run_id=discover_run_id,
                last_status="succeeded",
            )
        )
        session.commit()


def test_export_slo_snapshot_contains_required_sections(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'slo.db').as_posix()}"
    _seed(database_url, workspace_id="w1")
    payload = export_slo_snapshot(database_url=database_url, workspace_id="w1")
    assert payload["workspace_id"] == "w1"
    assert payload["schema_version"] == "slo.v1"
    assert payload["run_queue"]["depth"] == 1
    assert payload["denials"][0]["reason"] == "dataset_not_allowed"
    assert payload["review_latency"]["blocking_open_count"] == 1
    assert payload["sync_lag"]["active_target_db_id"] == "tdb-1"
    assert payload["data_freshness"][0]["dataset_id"] == "ds-1"


def test_render_slo_csv_includes_key_metrics(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'slo_csv.db').as_posix()}"
    _seed(database_url, workspace_id="w1")
    payload = export_slo_snapshot(database_url=database_url, workspace_id="w1")
    rendered = render_slo_csv(payload)
    assert rendered.splitlines()[0] == "section,metric,dimension,value"
    assert "denials,denial_count,dataset_not_allowed,1" in rendered
    assert "run_queue,depth,all,1" in rendered


def test_export_slo_snapshot_denies_sensitive_breakdown_for_analyst(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'slo_authz.db').as_posix()}"
    _seed(database_url, workspace_id="w1")
    try:
        export_slo_snapshot(
            database_url=database_url,
            workspace_id="w1",
            actor_role="analyst",
            include_sensitive_breakdown=True,
        )
    except PermissionError as exc:
        assert str(exc) == "role_not_allowed_for_sensitive_slo_export"
    else:
        raise AssertionError("Expected PermissionError for analyst sensitive export")


def test_export_slo_snapshot_supports_redacted_mode_for_analyst(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'slo_redacted.db').as_posix()}"
    _seed(database_url, workspace_id="w1")
    payload = export_slo_snapshot(
        database_url=database_url,
        workspace_id="w1",
        actor_role="analyst",
        include_sensitive_breakdown=False,
    )
    assert payload["sensitive_breakdown"] is False
    denials = payload["denials"]
    assert isinstance(denials, dict)
    assert denials["by_reason"][0]["reason"] == "redacted"
