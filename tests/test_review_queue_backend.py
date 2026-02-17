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
        database_url="sqlite:///./runtime/test_review_queue.db",
    )


def test_review_queue_create_list_decide() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "review", "profile": "starter", "security_baseline": "standard"},
    ).json()
    workspace_id = workspace["workspace_id"]

    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/proposals",
        json={
            "proposal_type": "pii_tag_proposal",
            "evidence_bundle_uri": "evidence://pii",
            "confidence": 0.7,
            "priority": "security_critical",
            "blocking": True,
        },
    ).json()
    task_id = created["task"]["task_id"]

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/review_tasks").json()
    assert any(task["task_id"] == task_id for task in listed)

    decision_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/review_tasks/{task_id}/decision",
        json={"decision": "approve", "actor_id": "user:steward"},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "approve"
