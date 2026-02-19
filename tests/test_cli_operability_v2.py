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


def _strip_runtime_timestamps(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _strip_runtime_timestamps(child)
            for key, child in value.items()
            if key not in {"generated_at_epoch", "started_epoch", "finished_epoch"}
        }
    if isinstance(value, list):
        return [_strip_runtime_timestamps(item) for item in value]
    return value


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
    assert payload["run_steps"]["failed_by_failure_code"]["FC-0003_STRICT_COMPLETENESS"] == 1
    assert payload["review_queue"]["blocking_open_tasks"] == 1
    assert payload["review_queue"]["oldest_blocking_tasks"]
    assert payload["suggested_next_actions"]
    assert "schemapilot slo export" in payload["slo_export_hint"]


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
        summary = json.loads(archive.read("meta/summary.json").decode("utf-8"))
        assert summary["manifest_hashes"]["status"] == "ok"
        assert summary["pack_versions"]
        redacted_settings = json.loads(
            archive.read("config/settings_redacted.json").decode("utf-8")
        )
        assert redacted_settings["audit_sink_target"] == "<redacted>"


def test_auditor_export_command_writes_governance_bundle(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ops_auditor.db').as_posix()}"
    _seed_workspace_state(database_url, workspace_id="w1")
    registry_path = tmp_path / "pack_registry.json"
    registry_path.write_text(json.dumps({"policies": []}), encoding="utf-8")
    output_path = tmp_path / "auditor_export.json"
    result = runner.invoke(
        app,
        [
            "auditor-export",
            "--database-url",
            database_url,
            "--pack-registry",
            registry_path.as_posix(),
            "--output",
            output_path.as_posix(),
            "--signing-key",
            "test-signing-key",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["bundle"]["schema_version"] == "v1"
    assert exported["signature"]["algorithm"] == "hmac-sha256"


def test_slo_export_command_outputs_json(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ops_slo.db').as_posix()}"
    _seed_workspace_state(database_url, workspace_id="w1")
    result = runner.invoke(
        app,
        ["slo", "export", "--workspace", "w1", "--database-url", database_url, "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["workspace_id"] == "w1"
    assert "run_queue" in payload
    assert "denials" in payload


def test_diag_bundle_structure_is_deterministic_except_timestamps(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ops_diag_det.db').as_posix()}"
    _seed_workspace_state(database_url, workspace_id="w1")
    config_path = tmp_path / "diag_det_config.json"
    config_path.write_text(
        json.dumps(
            {
                "profile": "team",
                "bind_address": "127.0.0.1",
                "auth_mode": "local",
                "database_url": database_url,
                "storage_root": (tmp_path / "storage").as_posix(),
            }
        ),
        encoding="utf-8",
    )
    first_bundle = tmp_path / "diag_1.zip"
    second_bundle = tmp_path / "diag_2.zip"
    for bundle in (first_bundle, second_bundle):
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
                bundle.as_posix(),
            ],
        )
        assert result.exit_code == 0
    with zipfile.ZipFile(first_bundle) as left, zipfile.ZipFile(second_bundle) as right:
        left_names = sorted(left.namelist())
        right_names = sorted(right.namelist())
        assert left_names == right_names
        for name in left_names:
            if not name.endswith(".json"):
                continue
            left_payload = json.loads(left.read(name).decode("utf-8"))
            right_payload = json.loads(right.read(name).decode("utf-8"))
            assert _strip_runtime_timestamps(left_payload) == _strip_runtime_timestamps(
                right_payload
            )


def test_slo_export_command_denies_sensitive_export_for_analyst(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ops_slo_authz.db').as_posix()}"
    _seed_workspace_state(database_url, workspace_id="w1")
    result = runner.invoke(
        app,
        [
            "slo",
            "export",
            "--workspace",
            "w1",
            "--database-url",
            database_url,
            "--role",
            "analyst",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1
