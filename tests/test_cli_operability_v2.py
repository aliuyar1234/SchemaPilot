from __future__ import annotations

import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from backend.shared_domain.audit_models import AccessDecision, AuditEvent, AuditOutboxEvent
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    Base,
    ReviewTask,
    RunRecord,
    RunStepRecord,
    Workspace,
)
from cli.schemapilot_cli.main import app

runner = CliRunner()


def _seed_workspace_state(database_url: str, *, workspace_id: str) -> None:
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        session.add(
            Workspace(
                workspace_id=workspace_id,
                name="Ops Workspace",
                profile="team",
                security_baseline="strict",
            )
        )
        run_id = new_ulid()
        session.add(
            RunRecord(
                run_id=run_id,
                workspace_id=workspace_id,
                run_type="discover",
                status="failed",
                input_refs_json={"source_ids": ["s1"]},
                output_refs_json={"error": "strict_ingest_completeness_failed"},
            )
        )
        session.add(
            RunStepRecord(
                run_step_id=new_ulid(),
                run_id=run_id,
                workspace_id=workspace_id,
                run_type="discover",
                step_key="ingest_profile_governance",
                step_order=20,
                depends_on_json=["discover_inventory"],
                status="failed",
                started_epoch=1,
                finished_epoch=2,
                duration_ms=1000,
                attempt_count=1,
                error_code="strict_ingest_completeness_failed",
                evidence_bundle_uri="evidence://w1/step-fail",
                details_json={"failure_count": 1},
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
            AuditOutboxEvent(
                outbox_event_id=new_ulid(),
                service="gateway",
                workspace_id=workspace_id,
                audit_event_id=audit_event_id,
                payload_json={"event_type": "gateway.query"},
                status="pending",
                attempt_count=1,
                last_error="audit_sink_unavailable",
            )
        )
        session.commit()


def test_analyze_command_reports_denials_and_run_steps(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ops.db').as_posix()}"
    _seed_workspace_state(database_url, workspace_id="w1")
    result = runner.invoke(
        app,
        ["analyze", "--workspace", "w1", "--database-url", database_url],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["policy_denials"]["total"] == 1
    assert payload["policy_denials"]["by_reason"][0]["reason"] == "dataset_not_allowed"
    assert payload["run_steps"]["by_status"]["failed"] == 1
    assert payload["review_queue"]["blocking_open_tasks"] == 1


def test_diag_bundle_command_writes_redacted_zip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ops_diag.db').as_posix()}"
    _seed_workspace_state(database_url, workspace_id="w1")
    config_path = tmp_path / "diag_config.json"
    config_path.write_text(
        json.dumps(
            {
                "profile": "team",
                "bind_address": "127.0.0.1",
                "auth_mode": "local",
                "database_url": database_url,
                "storage_root": (tmp_path / "storage").as_posix(),
                "audit_sink_target": "https://sink.example?token=test-token",
            }
        ),
        encoding="utf-8",
    )
    bundle_path = tmp_path / "diag.zip"
    result = runner.invoke(
        app,
        [
            "diag-bundle",
            "--workspace",
            "w1",
            "--database-url",
            database_url,
            "--config",
            config_path.as_posix(),
            "--output",
            bundle_path.as_posix(),
        ],
    )
    assert result.exit_code == 0
    assert bundle_path.exists()

    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        assert "analysis/workspace_analysis.json" in names
        assert "runs/recent_run_steps.json" in names
        redacted_settings = json.loads(
            archive.read("config/settings_redacted.json").decode("utf-8")
        )
        assert redacted_settings["audit_sink_target"] == "<redacted>"
