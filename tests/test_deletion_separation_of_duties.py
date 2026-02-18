from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _settings(tmp_path: Path, *, deletion_enabled: bool) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'deletion_sod.db').as_posix()}",
        retention_purge_root=(tmp_path / "storage").as_posix(),
        deletion_enabled=deletion_enabled,
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": name, "profile": "team", "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def test_deletion_endpoint_disabled_by_default(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_factory=lambda: _settings(tmp_path, deletion_enabled=False))
    )
    workspace_id = _create_workspace(client, "Deletion Disabled")
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions",
        json={"subject_selector": {"customer_id": "c1"}},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "deletion_disabled"


def test_deletion_workflow_enforces_separation_of_duties(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_factory=lambda: _settings(tmp_path, deletion_enabled=True))
    )
    workspace_id = _create_workspace(client, "Deletion SoD")

    request_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions",
        json={
            "subject_selector": {"customer_id": "c2"},
            "affected_snapshots": ["silver-1"],
            "affected_indexes": ["idx-1"],
        },
        headers=_headers("local-data-steward-token"),
    )
    assert request_response.status_code == 200
    deletion_request_id = str(request_response.json()["deletion_request_id"])

    self_approve_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/approve",
        json={"decision": "approve", "decision_reason": "ship it"},
        headers=_headers("local-data-steward-token"),
    )
    assert self_approve_response.status_code == 403
    assert (
        self_approve_response.json()["error"]["details"]["reason"]
        == "requester_cannot_self_approve"
    )

    approve_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/approve",
        json={"decision": "approve", "decision_reason": "approved by admin"},
        headers=_headers("local-platform-admin-token"),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    execute_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/execute",
        json={"output_root": tmp_path.as_posix()},
        headers=_headers("local-platform-admin-token"),
    )
    assert execute_response.status_code == 200
    body = execute_response.json()
    assert body["status"] == "executed"
    assert str(body["evidence_bundle_uri"]).startswith("evidence://")


def test_legal_hold_is_server_side_truth_for_deletions(tmp_path: Path) -> None:
    client = TestClient(
        create_app(settings_factory=lambda: _settings(tmp_path, deletion_enabled=True))
    )
    workspace_id = _create_workspace(client, "Deletion Legal Hold")

    policy_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/retention/policy",
        json={
            "retention_days": 30,
            "enabled": True,
            "purge_enabled": False,
            "legal_hold_active": True,
        },
        headers=_headers("local-platform-admin-token"),
    )
    assert policy_response.status_code == 200

    request_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions",
        json={
            "subject_selector": {"customer_id": "c3"},
            "affected_snapshots": ["gold-1"],
            "affected_indexes": ["search-1"],
            "legal_hold_active": False,
        },
        headers=_headers("local-data-steward-token"),
    )
    assert request_response.status_code == 200
    request_body = request_response.json()
    assert request_body["legal_hold_active"] is True
    deletion_request_id = str(request_body["deletion_request_id"])

    approve_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/approve",
        json={"decision": "approve", "decision_reason": "admin approval"},
        headers=_headers("local-platform-admin-token"),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "blocked"

    execute_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/deletions/{deletion_request_id}/execute",
        json={"output_root": tmp_path.as_posix()},
        headers=_headers("local-platform-admin-token"),
    )
    assert execute_response.status_code == 200
    body = execute_response.json()
    assert body["status"] == "blocked"
    assert body["reason"] == "legal_hold_active"
