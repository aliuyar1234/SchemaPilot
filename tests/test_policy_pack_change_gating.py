from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.audit_models import AccessDecision
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory


def _settings(tmp_path: Path, *, canary_enabled: bool = False) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'policy_pack_lifecycle.db').as_posix()}",
        policy_pack_canary_enabled=canary_enabled,
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient, *, name: str) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": name, "profile": "team", "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def test_policy_pack_change_requires_steward_or_admin_role(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client, name="Policy Role Guard")

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "missing_required_role"


def test_policy_pack_change_is_approval_gated_and_rollbackable(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client, name="Policy Lifecycle")

    first_request = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-data-steward-token"),
    )
    assert first_request.status_code == 200
    first_change_id = str(first_request.json()["change_request_id"])

    review_tasks = client.get(f"/api/v1/workspaces/{workspace_id}/review_tasks")
    assert review_tasks.status_code == 200
    assert any(
        task["priority"] == "security_critical"
        and task["blocking"] is True
        and task["proposal_type"] == "policy_pack_change_proposal"
        for task in review_tasks.json()
    )

    first_decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-requests/{first_change_id}/decision",
        json={"decision": "approve", "decision_reason": "approved for rollout"},
        headers=_headers("local-platform-admin-token"),
    )
    assert first_decision.status_code == 200
    assert first_decision.json()["status"] == "applied"
    effective = client.get(
        f"/api/v1/workspaces/{workspace_id}/policy-pack",
        headers=_headers("local-platform-admin-token"),
    )
    assert effective.status_code == 200
    assert effective.json()["pack_id"] == "enterprise_ai_assistant"
    assert int(effective.json()["version"]) == 1

    second_request = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "starter_local_team"},
        headers=_headers("local-data-steward-token"),
    )
    assert second_request.status_code == 200
    second_change_id = str(second_request.json()["change_request_id"])
    second_decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-requests/{second_change_id}/decision",
        json={"decision": "approve", "decision_reason": "rollback test seed"},
        headers=_headers("local-platform-admin-token"),
    )
    assert second_decision.status_code == 200
    effective_second = client.get(
        f"/api/v1/workspaces/{workspace_id}/policy-pack",
        headers=_headers("local-platform-admin-token"),
    )
    assert effective_second.status_code == 200
    assert effective_second.json()["pack_id"] == "starter_local_team"
    assert int(effective_second.json()["version"]) == 2

    rollback = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/rollback",
        headers=_headers("local-platform-admin-token"),
    )
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"
    rollback_effective = rollback.json()["effective_policy_pack"]
    assert rollback_effective["pack_id"] == "enterprise_ai_assistant"
    assert int(rollback_effective["version"]) == 3

    gateway_settings = _settings(tmp_path)
    gateway_client = TestClient(create_gateway_app(settings_factory=lambda: gateway_settings))
    query_response = gateway_client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_headers("local-analyst-token"),
    )
    assert query_response.status_code == 200
    provenance = query_response.json()["provenance"]
    assert provenance["policy_pack"]["pack_id"] == "enterprise_ai_assistant"
    assert int(provenance["policy_pack"]["version"]) == 3

    session = get_session_factory(gateway_settings.database_url)()
    try:
        decisions = session.execute(select(AccessDecision)).scalars().all()
        assert any(
            isinstance(decision.resources_json, dict)
            and isinstance(decision.resources_json.get("policy_pack"), dict)
            and decision.resources_json["policy_pack"].get("pack_id")
            == "enterprise_ai_assistant"
            for decision in decisions
        )
    finally:
        session.close()


def test_policy_pack_canary_requires_promotion_before_apply(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path, canary_enabled=True)))
    workspace_id = _create_workspace(client, name="Policy Canary")
    change_request = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-request",
        json={"pack_id": "enterprise_ai_assistant"},
        headers=_headers("local-data-steward-token"),
    )
    assert change_request.status_code == 200
    change_id = str(change_request.json()["change_request_id"])
    decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/change-requests/{change_id}/decision",
        json={"decision": "approve", "decision_reason": "start canary"},
        headers=_headers("local-platform-admin-token"),
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "canary_active"
    canary = client.get(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/canary",
        headers=_headers("local-platform-admin-token"),
    )
    assert canary.status_code == 200
    assert canary.json()["status"] == "canary_active"
    promote = client.post(
        f"/api/v1/workspaces/{workspace_id}/policy-pack/canary/promote",
        headers=_headers("local-platform-admin-token"),
    )
    assert promote.status_code == 200
    assert promote.json()["status"] == "promoted"
    effective = client.get(
        f"/api/v1/workspaces/{workspace_id}/policy-pack",
        headers=_headers("local-platform-admin-token"),
    )
    assert effective.status_code == 200
    assert effective.json()["pack_id"] == "enterprise_ai_assistant"
