from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.evidence_store import parse_evidence_uri, store_evidence_bundle


def _safe_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_workspace_source_run_flow() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))

    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Default Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
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
        headers=_admin_headers(),
    )
    assert source_response.status_code == 200
    assert source_response.json()["workspace_id"] == workspace_id

    run_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/runs",
        json={"run_type": "discover"},
        headers=_admin_headers(),
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run_id"]

    run_get_response = client.get(f"/api/v1/workspaces/{workspace_id}/runs/{run_id}")
    assert run_get_response.status_code == 200
    assert run_get_response.json()["run_type"] == "discover"
    assert isinstance(run_get_response.json()["run_steps"], list)

    run_steps_response = client.get(f"/api/v1/workspaces/{workspace_id}/runs/{run_id}/steps")
    assert run_steps_response.status_code == 200
    assert isinstance(run_steps_response.json(), list)


def test_workspace_accepts_dropzone_source_type() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Dropzone Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_id = workspace_response.json()["workspace_id"]
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "dropzone",
            "scope": {"root_path": "/tmp/dropzone", "required_files": ["invoices.csv"]},
            "display_name": "Dropzone",
        },
        headers=_admin_headers(),
    )
    assert source_response.status_code == 200
    body = source_response.json()
    assert body["source_type"] == "dropzone"


def test_workspace_accepts_sharepoint_source_type() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={
            "name": "SharePoint Workspace",
            "profile": "starter",
            "security_baseline": "standard",
        },
        headers=_admin_headers(),
    )
    workspace_id = workspace_response.json()["workspace_id"]
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "sharepoint",
            "scope": {"root_path": "/sites/team/shared-documents"},
            "display_name": "SharePoint Exports",
        },
        headers=_admin_headers(),
    )
    assert source_response.status_code == 200
    body = source_response.json()
    assert body["source_type"] == "sharepoint"


def test_workspace_accepts_smb_source_type() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "SMB Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_id = workspace_response.json()["workspace_id"]
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "smb",
            "scope": {"root_path": "/mnt/smb/team-share"},
            "display_name": "SMB Share",
        },
        headers=_admin_headers(),
    )
    assert source_response.status_code == 200
    body = source_response.json()
    assert body["source_type"] == "smb"


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
        headers=_admin_headers(),
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
        headers=_admin_headers(),
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
        headers=_admin_headers(),
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


def test_evidence_endpoint_returns_stored_bundle() -> None:
    settings = _safe_settings()
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Evidence Workspace", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    )
    workspace_id = workspace_response.json()["workspace_id"]

    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=settings.storage_root,
        bundle_type="profile",
        payload={"dataset_id": "d1", "profile": {"row_count_sampled": 1}},
    )
    _, evidence_id = parse_evidence_uri(stored.evidence_bundle_uri)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/evidence/{evidence_id}",
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == workspace_id
    assert body["evidence_id"] == evidence_id
