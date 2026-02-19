from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import ReviewTask, TargetDbPlan, TargetDbState


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_control_target_db.db",
    )


def _settings_rls_enabled() -> Settings:
    settings = _settings()
    return Settings(**{**settings.__dict__, "target_db_rls_enabled": True})


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def _create_workspace(client: TestClient) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "Target DB Workspace", "profile": "team", "security_baseline": "strict"},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def test_target_db_profile_crud_flow() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)

    create_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={
            "name": "serving-db",
            "db_type": "postgres",
            "mode": "managed",
            "connection": {"host": "postgres", "port": 5432},
            "credential_refs": {},
        },
        headers=_admin_headers(),
    )
    assert create_response.status_code == 200
    target_db = create_response.json()["target_db"]
    assert target_db["workspace_id"] == workspace_id
    target_db_id = target_db["target_db_id"]

    list_response = client.get(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        headers=_admin_headers(),
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert isinstance(listed, list)
    assert listed[0]["target_db_id"] == target_db_id

    get_response = client.get(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}",
        headers=_admin_headers(),
    )
    assert get_response.status_code == 200
    profile = get_response.json()
    assert profile["target_db_id"] == target_db_id
    assert profile["state"]["active_target_db_id"] == target_db_id

    disable_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}:disable",
        json={},
        headers=_admin_headers(),
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["target_db"]["status"] == "disabled"


def test_target_db_plan_apply_requires_checksum_match() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)
    create_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    target_db_id = create_response.json()["target_db"]["target_db_id"]

    plan_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/provision/plan",
        json={},
        headers=_admin_headers(),
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["plan"]

    mismatch_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/provision/apply",
        json={
            "plan_id": plan["plan_id"],
            "expected_plan_checksum": "sha256:deadbeef",
        },
        headers=_admin_headers(),
    )
    assert mismatch_response.status_code == 403
    body = mismatch_response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "plan_checksum_mismatch"


def test_target_db_sync_status_returns_dataset_rows() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)
    create_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    target_db_id = create_response.json()["target_db"]["target_db_id"]

    sync_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync:run",
        json={"datasets": ["ds_invoices", "ds_customers"], "strict_completeness": True},
        headers=_admin_headers(),
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["run_id"]

    status_response = client.get(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/status",
        headers=_admin_headers(),
    )
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["target_db_id"] == target_db_id
    assert len(body["datasets"]) == 2


def test_target_db_migration_apply_requires_approved_review_task() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)
    create_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    target_db_id = create_response.json()["target_db"]["target_db_id"]

    plan_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/plan",
        json={"requires_approval": True},
        headers=_admin_headers(),
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["plan"]
    session_factory = get_session_factory(_settings().database_url)
    approval_task_id = new_ulid()
    with session_factory() as session:
        session.add(
            ReviewTask(
                task_id=approval_task_id,
                workspace_id=workspace_id,
                priority="security_critical",
                subject_ref=str(plan["plan_id"]),
                status="open",
                blocking=True,
            )
        )
        plan_row = session.get(TargetDbPlan, str(plan["plan_id"]))
        assert plan_row is not None
        payload = dict(plan_row.payload_json)
        payload["approval_task_id"] = approval_task_id
        plan_row.payload_json = payload
        session.commit()

    blocked_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/apply",
        json={
            "plan_id": plan["plan_id"],
            "expected_plan_checksum": plan["plan_checksum"],
        },
        headers=_admin_headers(),
    )
    assert blocked_response.status_code == 403
    blocked = blocked_response.json()
    assert blocked["error"]["details"]["reason"] == "approval_required"

    decision_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/review_tasks/{approval_task_id}/decision",
        json={"decision": "approve", "decision_reason": "safe"},
        headers=_admin_headers(),
    )
    assert decision_response.status_code == 200

    apply_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/migrations/apply",
        json={
            "plan_id": plan["plan_id"],
            "expected_plan_checksum": plan["plan_checksum"],
        },
        headers=_admin_headers(),
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["run_id"]


def test_target_db_sync_schedule_create_and_list() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)
    create_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    target_db_id = create_response.json()["target_db"]["target_db_id"]

    schedule_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/schedules",
        json={
            "schedule_expression": "*/5 * * * *",
            "datasets": ["ds_orders", "ds_customers"],
            "strict_completeness": True,
            "enabled": True,
            "max_runtime_seconds": 120,
            "max_rows_per_dataset": 5000,
            "max_datasets": 4,
        },
        headers=_admin_headers(),
    )
    assert schedule_response.status_code == 200
    schedule = schedule_response.json()
    assert schedule["run_type"] == "TARGET_DB_SYNC_RUN"
    assert schedule["input_refs"]["target_db_id"] == target_db_id

    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/sync/schedules",
        headers=_admin_headers(),
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["input_refs"]["target_db_id"] == target_db_id


def test_target_db_cutover_switches_active_target() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)
    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "primary-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    assert first.status_code == 200
    first_target_db_id = first.json()["target_db"]["target_db_id"]
    second = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "shadow-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    assert second.status_code == 200
    second_target_db_id = second.json()["target_db"]["target_db_id"]
    cutover = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/cutover",
        json={
            "from_target_db_id": first_target_db_id,
            "to_target_db_id": second_target_db_id,
        },
        headers=_admin_headers(),
    )
    assert cutover.status_code == 200
    body = cutover.json()
    assert body["to_target_db_id"] == second_target_db_id

    session_factory = get_session_factory(_settings().database_url)
    with session_factory() as session:
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        assert state_row.active_target_db_id == second_target_db_id


def test_target_db_rls_endpoints_require_module_enable_flag() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace_id = _create_workspace(client)
    create_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    target_db_id = create_response.json()["target_db"]["target_db_id"]

    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/target-dbs/{target_db_id}/rls/plan",
        json={},
        headers=_admin_headers(),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["reason"] == "module_disabled"

    enabled_client = TestClient(create_app(settings_factory=_settings_rls_enabled))
    enabled_workspace = _create_workspace(enabled_client)
    enabled_profile = enabled_client.post(
        f"/api/v1/workspaces/{enabled_workspace}/target-dbs",
        json={"name": "serving-db", "db_type": "postgres", "mode": "managed"},
        headers=_admin_headers(),
    )
    enabled_target_db_id = enabled_profile.json()["target_db"]["target_db_id"]
    allowed = enabled_client.post(
        f"/api/v1/workspaces/{enabled_workspace}/target-dbs/{enabled_target_db_id}/rls/plan",
        json={},
        headers=_admin_headers(),
    )
    assert allowed.status_code == 200
    assert allowed.json()["run_id"]
