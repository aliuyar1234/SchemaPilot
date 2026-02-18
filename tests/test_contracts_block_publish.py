from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.contract_reports import write_build_contract_report


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_contracts_block_publish.db",
    )


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_publish_fails_closed_without_contract_report_and_creates_quality_task() -> None:
    settings = _settings()
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "contracts", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]

    publish = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-001/publish",
        json={},
        headers=_admin_headers(),
    )
    assert publish.status_code == 200
    body = publish.json()
    assert body["status"] == "blocked"
    assert body["gate_reason"] == "contract_failure"
    assert body["contracts_report_present"] is False
    assert body["contracts_passed"] is False

    tasks = client.get(f"/api/v1/workspaces/{workspace_id}/review_tasks").json()
    assert any(
        task["priority"] == "quality_critical"
        and task["blocking"] is True
        and task["proposal_type"] == "contract_failure_proposal"
        for task in tasks
    )
    first_task_count = len(tasks)

    publish_again = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-001/publish",
        json={},
        headers=_admin_headers(),
    )
    assert publish_again.status_code == 200
    tasks_after_again = client.get(f"/api/v1/workspaces/{workspace_id}/review_tasks").json()
    assert len(tasks_after_again) == first_task_count


def test_publish_uses_server_side_contract_report_and_allows_pass_case() -> None:
    settings = _settings()
    client = TestClient(create_app(settings_factory=lambda: settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "contracts-pass", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]
    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build-002",
        contracts_passed=True,
        failures=[],
        storage_root=settings.storage_root,
    )

    publish = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-002/publish",
        json={},
        headers=_admin_headers(),
    )
    assert publish.status_code == 200
    body = publish.json()
    assert body["status"] == "published"
    assert body["gate_reason"] == "all_gates_passed"
    assert body["contracts_report_present"] is True
    assert body["contracts_passed"] is True
