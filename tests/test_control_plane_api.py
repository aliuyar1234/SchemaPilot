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


def test_control_plane_not_found_responses_follow_error_contract() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    response = client.get("/api/v1/workspaces/missing-workspace")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Workspace not found."
    assert "request_id" in body["error"]


def test_create_run_on_missing_workspace_returns_not_found() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/workspaces/missing-workspace/runs",
        json={"run_type": "discover"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"]["workspace_id"] == "missing-workspace"


def test_demo_bootstrap_creates_workspace_and_review_task() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/onboarding/demo_bootstrap",
        json={"workspace_name": "Demo Boot"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workspace"]["name"] == "Demo Boot"
    assert body["review_task"]["blocking"] is True
    assert "first_query_example" in body


def test_policy_packs_endpoint_returns_templates() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    response = client.get("/api/v1/policy-packs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert any(item["id"] == "starter_local_team" for item in body)


def test_dataset_endpoints_return_expected_contracts() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Dataset Workspace", "profile": "starter", "security_baseline": "standard"},
    )
    workspace_id = workspace_response.json()["workspace_id"]

    list_response = client.get(f"/api/v1/workspaces/{workspace_id}/datasets")
    assert list_response.status_code == 200
    assert list_response.json() == []

    get_response = client.get(f"/api/v1/workspaces/{workspace_id}/datasets/missing-dataset")
    assert get_response.status_code == 404
    body = get_response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Dataset not found."
    assert body["error"]["details"]["workspace_id"] == workspace_id
