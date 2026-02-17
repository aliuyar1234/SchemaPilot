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
        database_url="sqlite:///./runtime/test_build_gating.db",
    )


def test_gold_publish_blocked_when_blocking_review_task_open() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "gating", "profile": "starter", "security_baseline": "standard"},
    ).json()
    workspace_id = workspace["workspace_id"]

    client.post(
        f"/api/v1/workspaces/{workspace_id}/proposals",
        json={
            "proposal_type": "schema_proposal",
            "evidence_bundle_uri": "evidence://drift",
            "confidence": 0.4,
            "priority": "quality_critical",
            "blocking": True,
        },
    )

    publish = client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-123/publish",
        json={"contracts_passed": True},
    )
    assert publish.status_code == 200
    body = publish.json()
    assert body["status"] == "blocked"
    assert body["gate_reason"] == "blocking_review_tasks"
