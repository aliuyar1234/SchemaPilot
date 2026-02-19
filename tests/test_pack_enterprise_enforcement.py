from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.control_plane.app import create_app
from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from tools.pack_lint import sign_pack_registry


def _write_matrix(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "matrix_version": "v1",
                "runtime_version": "0.1.0",
                "sections": {
                    "policy_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    },
                    "semantic_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    },
                    "template_packs": {
                        "current_schema_version": "v2",
                        "supported_schema_versions": ["v1", "v2"],
                    },
                    "connector_examples": {
                        "current_schema_version": "v1",
                        "supported_schema_versions": ["v1"],
                    },
                },
                "migrations": [],
            }
        ),
        encoding="utf-8",
    )


def _write_registry(path: Path, *, include_signature: bool) -> None:
    payload: dict[str, object] = {
        "registry_version": "v1",
        "policy_packs": [
            {
                "pack_id": "enterprise_ai_assistant",
                "version": "1.0.0",
                "schema_version": "v2",
                "path": "packs/policy/enterprise_ai_assistant.json",
            }
        ],
        "semantic_packs": [],
        "template_packs": [],
        "connector_examples": [],
    }
    if include_signature:
        payload["policy_packs"][0]["signature"] = {  # type: ignore[index]
            "algorithm": "hmac-sha256",
            "key_id": "test",
            "value": "",
        }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _settings(
    tmp_path: Path, *, registry_path: Path, matrix_path: Path, signing_key: str = "test-key"
) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'pack_enforcement.db').as_posix()}",
        pack_registry_path=registry_path.as_posix(),
        pack_matrix_path=matrix_path.as_posix(),
        pack_signing_key=signing_key,
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient, *, profile: str, name: str) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": name, "profile": profile, "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def _audit_events(database_url: str) -> list[AuditEvent]:
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        return session.execute(select(AuditEvent)).scalars().all()


def test_team_workspace_warns_for_unsigned_pack_but_allows_request(tmp_path: Path) -> None:
    pack_file = tmp_path / "packs" / "policy" / "enterprise_ai_assistant.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(json.dumps({"pack_id": "enterprise_ai_assistant"}), encoding="utf-8")
    matrix_path = tmp_path / "matrix.json"
    _write_matrix(matrix_path)
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, include_signature=False)
    settings = _settings(tmp_path, registry_path=registry_path, matrix_path=matrix_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, profile="team", name="Pack Warn Team")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 200
    verification = response.json()["pack_verification"]
    assert verification["verified"] is False
    assert verification["enforcement"] == "warn"

    events = _audit_events(settings.database_url)
    verify_events = [event for event in events if event.event_type == "policy_pack.verify"]
    assert verify_events
    assert verify_events[-1].event_json["verified"] is False


def test_enterprise_workspace_blocks_unsigned_pack_change(tmp_path: Path) -> None:
    pack_file = tmp_path / "packs" / "policy" / "enterprise_ai_assistant.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(json.dumps({"pack_id": "enterprise_ai_assistant"}), encoding="utf-8")
    matrix_path = tmp_path / "matrix.json"
    _write_matrix(matrix_path)
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, include_signature=False)
    settings = _settings(tmp_path, registry_path=registry_path, matrix_path=matrix_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, profile="enterprise", name="Pack Enforce Enterprise")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 403
    details = response.json()["error"]["details"]
    assert details["reason"] == "pack_verification_failed"

    events = _audit_events(settings.database_url)
    verify_events = [event for event in events if event.event_type == "policy_pack.verify"]
    assert verify_events
    assert verify_events[-1].event_json["verified"] is False
    assert verify_events[-1].event_json["enforcement"] == "enforce"


def test_enterprise_workspace_allows_signed_pack_change(tmp_path: Path) -> None:
    pack_file = tmp_path / "packs" / "policy" / "enterprise_ai_assistant.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(
        json.dumps({"pack_id": "enterprise_ai_assistant", "schema_version": "v2"}),
        encoding="utf-8",
    )
    matrix_path = tmp_path / "matrix.json"
    _write_matrix(matrix_path)
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, include_signature=False)
    sign_errors = sign_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="matrix.json",
        signing_key="test-key",
        key_id="test",
    )
    assert sign_errors == []
    settings = _settings(tmp_path, registry_path=registry_path, matrix_path=matrix_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, profile="enterprise", name="Pack Signed Enterprise")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 200
    verification = response.json()["pack_verification"]
    assert verification["verified"] is True
    assert verification["enforcement"] == "enforce"


def test_signed_pack_with_legacy_schema_is_blocked_by_compatibility_gate(tmp_path: Path) -> None:
    pack_file = tmp_path / "packs" / "policy" / "enterprise_ai_assistant.json"
    pack_file.parent.mkdir(parents=True, exist_ok=True)
    pack_file.write_text(
        json.dumps({"pack_id": "enterprise_ai_assistant", "schema_version": "v1"}),
        encoding="utf-8",
    )
    matrix_path = tmp_path / "matrix.json"
    _write_matrix(matrix_path)
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, include_signature=False)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["policy_packs"][0]["schema_version"] = "v1"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    sign_errors = sign_pack_registry(
        tmp_path,
        registry_path="registry.json",
        matrix_path="matrix.json",
        signing_key="test-key",
        key_id="test",
    )
    assert sign_errors == []
    settings = _settings(tmp_path, registry_path=registry_path, matrix_path=matrix_path)
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_id = _create_workspace(client, profile="enterprise", name="Pack Compat Blocked")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 403
    details = response.json()["error"]["details"]
    assert details["reason"] == "pack_compatibility_failed"
    assert details["requires_migration"] is True
