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


def test_publish_and_rollback_update_target_db_state_snapshot() -> None:
    settings = _settings()
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "gold-target-db", "profile": "team", "security_baseline": "strict"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]
    target_db = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={
            "name": "serving-db",
            "db_type": "postgres",
            "mode": "managed",
            "connection": {"schema": "gold_serving"},
        },
        headers=_admin_headers(),
    ).json()["target_db"]
    target_db_id = str(target_db["target_db_id"])

    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build-1",
        contracts_passed=True,
        failures=[],
        storage_root=settings.storage_root,
    )
    publish_1 = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-1/publish",
        json={
            "snapshot_id": "snap-1",
            "model_name": "orders",
            "target_db_id": target_db_id,
        },
        headers=_admin_headers(),
    )
    assert publish_1.status_code == 200
    published_1 = publish_1.json()
    assert published_1["target_db_state_after"]["current_build_id"] == "build-1"
    assert published_1["target_db_state_after"]["current_schema_ref"] == "gold_serving"

    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build-2",
        contracts_passed=True,
        failures=[],
        storage_root=settings.storage_root,
    )
    publish_2 = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-2/publish",
        json={
            "snapshot_id": "snap-2",
            "model_name": "orders",
            "target_db_id": target_db_id,
        },
        headers=_admin_headers(),
    )
    assert publish_2.status_code == 200
    assert publish_2.json()["target_db_state_after"]["current_build_id"] == "build-2"

    rollback = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-1/rollback",
        headers=_admin_headers(),
    )
    assert rollback.status_code == 200
    rolled_back = rollback.json()
    assert rolled_back["target_db_state_after"]["current_build_id"] == "build-1"
    assert rolled_back["target_db_state_after"]["current_schema_ref"] == "gold_serving"
