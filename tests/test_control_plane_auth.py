from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_control_auth.db",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_control_plane_denies_missing_token_for_mutation() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "auth", "profile": "starter", "security_baseline": "standard"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_or_invalid_auth_token"


def test_control_plane_denies_invalid_token_for_mutation() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "auth", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_headers("not-a-valid-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_or_invalid_auth_token"


def test_control_plane_denies_insufficient_role_for_workspace_create() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "auth", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_required_role"
    assert "platform_admin" in body["error"]["details"]["required_roles"]


def test_control_plane_allows_admin_and_steward_roles_for_mutating_flows() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "auth-ok", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_headers("local-platform-admin-token"),
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["workspace_id"]

    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": "/tmp/data"},
            "display_name": "Exports",
        },
        headers=_auth_headers("local-data-steward-token"),
    )
    assert source_response.status_code == 200


def test_control_plane_denies_missing_token_for_evidence_read() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "auth-evidence", "profile": "starter", "security_baseline": "standard"},
        headers=_auth_headers("local-platform-admin-token"),
    )
    workspace_id = workspace_response.json()["workspace_id"]
    response = client.get(f"/api/v1/workspaces/{workspace_id}/evidence/missing")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "missing_or_invalid_auth_token"
