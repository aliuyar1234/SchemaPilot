from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _safe_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
    )


def test_workspace_source_run_flow() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))

    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Default Workspace", "profile": "starter", "security_baseline": "standard"},
    )
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()
    workspace_id = workspace["workspace_id"]

    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": "/tmp/data"},
            "display_name": "Exports",
        },
    )
    assert source_response.status_code == 200
    assert source_response.json()["workspace_id"] == workspace_id

    run_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/runs",
        json={"run_type": "discover"},
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    run_get_response = client.get(f"/api/v1/workspaces/{workspace_id}/runs/{run_id}")
    assert run_get_response.status_code == 200
    assert run_get_response.json()["run_type"] == "discover"
