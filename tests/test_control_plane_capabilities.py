from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import RunRecord


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'cp_capabilities.db').as_posix()}",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "CAP Workspace", "profile": "team", "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def _create_workspace_with_profile(client: TestClient, *, profile: str) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={
            "name": f"CAP Workspace {profile}",
            "profile": profile,
            "security_baseline": "strict",
        },
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def _create_target_db(client: TestClient, workspace_id: str) -> str:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["target_db"]["target_db_id"])


def test_query_budgets_roundtrip(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    configured = client.post(
        f"/api/v1/workspaces/{workspace_id}/query-budgets",
        json={"default_bytes": 12345, "per_role_bytes": {"analyst": 5000}},
        headers=_headers("local-platform-admin-token"),
    )
    assert configured.status_code == 200
    fetched = client.get(
        f"/api/v1/workspaces/{workspace_id}/query-budgets",
        headers=_headers("local-platform-admin-token"),
    )
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["default_bytes"] == 12345
    assert body["per_role_bytes"]["analyst"] == 5000


def test_access_request_approve_creates_policy_task(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/access-requests",
        json={"dataset_id": "dataset-1", "requested_role": "analyst"},
        headers=_headers("local-analyst-token"),
    )
    assert created.status_code == 200
    request_id = str(created.json()["request_id"])
    decided = client.post(
        f"/api/v1/workspaces/{workspace_id}/access-requests/{request_id}/decision",
        json={"decision": "approve", "decision_reason": "needed"},
        headers=_headers("local-data-steward-token"),
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "approved"
    assert "generated_task" in body


def test_breakglass_team_single_approval_creates_grant(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests",
        json={"actor_id": "analyst-1", "ttl_seconds": 600},
        headers=_headers("local-data-steward-token"),
    )
    assert created.status_code == 200
    request_id = str(created.json()["request_id"])
    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve",
        json={"decision": "approve"},
        headers=_headers("local-data-steward-token"),
    )
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "active"
    assert body["grant_policy_id"]


def test_breakglass_enterprise_dual_approval_creates_grant(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace_with_profile(client, profile="enterprise")
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests",
        json={"actor_id": "analyst-1", "ttl_seconds": 600},
        headers=_headers("local-data-steward-token"),
    )
    assert created.status_code == 200
    request_id = str(created.json()["request_id"])
    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve",
        json={"decision": "approve"},
        headers=_headers("local-data-steward-token"),
    )
    assert first.status_code == 200
    assert first.json()["status"] == "pending"
    assert "grant_policy_id" not in first.json()
    second = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve",
        json={"decision": "approve"},
        headers=_headers("local-platform-admin-token"),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "active"
    assert body["grant_policy_id"]


def test_breakglass_ttl_exceed_is_blocked(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests",
        json={"actor_id": "analyst-1", "ttl_seconds": 999999},
        headers=_headers("local-data-steward-token"),
    )
    assert created.status_code == 403
    details = created.json()["error"]["details"]
    assert details["reason"] == "invalid_breakglass_ttl"


def test_breakglass_approve_requires_steward_or_admin_role(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests",
        json={"actor_id": "analyst-1", "ttl_seconds": 600},
        headers=_headers("local-data-steward-token"),
    )
    assert created.status_code == 200
    request_id = str(created.json()["request_id"])
    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve",
        json={"decision": "approve"},
        headers=_headers("local-analyst-token"),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["reason"] == "missing_required_role"


def test_glossary_generate_and_export(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    generated = client.post(
        f"/api/v1/workspaces/{workspace_id}/glossary/generate",
        headers=_headers("local-data-steward-token"),
    )
    assert generated.status_code == 200
    exported = client.get(
        f"/api/v1/workspaces/{workspace_id}/glossary/export?format=markdown",
        headers=_headers("local-analyst-token"),
    )
    assert exported.status_code == 200
    assert exported.json()["format"] == "markdown"


def test_alerts_test_endpoint_returns_accepted(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/alerts/test",
        json={"severity": "critical", "reason": "unit_test"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "emitted"


def test_lineage_export_returns_graph_payload(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/lineage/export",
        json={"sql_text": "select revenue as metric_revenue from finance"},
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lineage_available"] is True
    assert "nodes" in body["graph"]
    assert "edges" in body["graph"]


def test_promotion_export_import_signature_gate(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    exported = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/export",
        headers=_headers("local-platform-admin-token"),
    )
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["bundle_checksum"]
    assert payload["attestation"]["action"] == "export"
    imported = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/import",
        json=payload,
        headers=_headers("local-platform-admin-token"),
    )
    assert imported.status_code == 200
    assert imported.json()["attestation"]["action"] == "import"
    assert imported.json()["bundle_checksum"] == payload["bundle_checksum"]
    tampered = dict(payload)
    bundle = dict(payload["bundle"])
    bundle["workspace_profile"] = "tampered"
    tampered["bundle"] = bundle
    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/import",
        json=tampered,
        headers=_headers("local-platform-admin-token"),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["reason"] == "promotion_bundle_checksum_mismatch"


def test_promotion_import_requires_policy_reports_for_enterprise_workspace(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace_with_profile(client, profile="enterprise")
    exported = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/export",
        headers=_headers("local-platform-admin-token"),
    )
    assert exported.status_code == 200
    payload = exported.json()
    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/import",
        json=payload,
        headers=_headers("local-platform-admin-token"),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["reason"] == "promotion_policy_reports_required"

    report = {
        "workspace_id": workspace_id,
        "scenario_count": 1,
        "scenarios": [
            {
                "id": "promotion-safe",
                "result": "allow",
                "reason": "allow",
                "applied_masks": {},
                "applied_filters": {},
            }
        ],
    }
    allowed = client.post(
        f"/api/v1/workspaces/{workspace_id}/promotion/import",
        json={
            **payload,
            "before_policy_report": report,
            "after_policy_report": report,
            "protected_scenario_ids": ["promotion-safe"],
        },
        headers=_headers("local-platform-admin-token"),
    )
    assert allowed.status_code == 200
    assert allowed.json()["policy_diff"]["status"] == "unchanged"


def test_target_db_rotate_credentials_creates_run(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client)
    target_db_id = _create_target_db(client, workspace_id)
    rotate = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/credentials/rotate",
        json={"reason": "test"},
        headers=_headers("local-platform-admin-token"),
    )
    assert rotate.status_code == 200
    run_id = str(rotate.json()["run_id"])
    session = get_session_factory(settings.database_url)()
    try:
        row = session.execute(
            select(RunRecord).where(RunRecord.run_id == run_id)
        ).scalar_one_or_none()
        assert row is not None
        assert row.run_type == "TARGET_DB_ROTATE_CREDENTIALS"
    finally:
        session.close()


def test_target_db_rotate_credentials_blocks_missing_external_refs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "ext-db", "db_type": "postgres", "mode": "external"},
        headers=_headers("local-platform-admin-token"),
    )
    assert created.status_code == 200
    target_db_id = str(created.json()["target_db"]["target_db_id"])
    rotate = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/credentials/rotate",
        json={"reason": "drill"},
        headers=_headers("local-platform-admin-token"),
    )
    assert rotate.status_code == 403
    details = rotate.json()["error"]["details"]
    assert details["reason"] == "target_db_rotation_prerequisites_missing"
    assert details["missing_roles"] == ["reader", "writer"]


def test_publish_response_contains_build_attestation(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-attest/publish",
        json={},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 200
    attestation = response.json()["build_attestation"]
    assert attestation["algorithm"] == "HMAC-SHA256"
    assert attestation["signature"]


def test_publish_blocks_when_attestation_required_but_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCHEMAPILOT_BUILD_ATTESTATION_REQUIRED", "true")
    monkeypatch.delenv("SCHEMAPILOT_BUILD_ATTESTATION_KEY", raising=False)
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-attest-required/publish",
        json={},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "build_attestation_key_required"
