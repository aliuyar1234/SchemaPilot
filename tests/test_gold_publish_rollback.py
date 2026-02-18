from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.contract_reports import write_build_contract_report
from backend.shared_domain.gold_pointer import load_latest_gold_pointer


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_gold_publish_rollback.db",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_gold_publish_updates_pointer_and_rollback_restores_previous_build() -> None:
    settings = _settings()
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "gold", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]

    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build-a",
        contracts_passed=True,
        failures=[],
        storage_root=settings.storage_root,
    )
    publish_a = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-a/publish",
        json={"snapshot_id": "snap-a", "model_name": "orders"},
        headers=_admin_headers(),
    )
    assert publish_a.status_code == 200
    assert publish_a.json()["status"] == "published"

    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build-b",
        contracts_passed=True,
        failures=[],
        storage_root=settings.storage_root,
    )
    publish_b = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-b/publish",
        json={"snapshot_id": "snap-b", "model_name": "orders"},
        headers=_admin_headers(),
    )
    assert publish_b.status_code == 200
    assert publish_b.json()["status"] == "published"

    latest_before = load_latest_gold_pointer(
        workspace_id=workspace_id,
        storage_root=settings.storage_root,
    )
    assert latest_before is not None
    assert latest_before["build_id"] == "build-b"

    rollback = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-a/rollback",
        headers=_admin_headers(),
    )
    assert rollback.status_code == 200
    rollback_body = rollback.json()
    assert rollback_body["status"] == "rolled_back"
    assert rollback_body["rollback"]["rolled_back_to"]["build_id"] == "build-a"

    latest_after = load_latest_gold_pointer(
        workspace_id=workspace_id,
        storage_root=settings.storage_root,
    )
    assert latest_after is not None
    assert latest_after["build_id"] == "build-a"


def test_gold_rollback_returns_not_found_for_unknown_target() -> None:
    settings = _settings()
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "gold-not-found", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/missing-build/rollback",
        headers=_admin_headers(),
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Rollback target not found."
