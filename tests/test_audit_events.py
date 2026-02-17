from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.control_plane import db_models
from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory


def _safe_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_audit.db",
    )


def test_create_operations_emit_audit_events() -> None:
    app = create_app(settings_factory=_safe_settings)
    client = TestClient(app)

    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "Audit WS", "profile": "starter", "security_baseline": "standard"},
    )
    workspace_id = workspace_response.json()["workspace_id"]
    source_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources",
        json={
            "source_type": "filesystem",
            "scope": {"root_path": "/tmp"},
            "display_name": "Exports",
        },
    )
    source_id = source_response.json()["source_id"]
    client.patch(
        f"/api/v1/workspaces/{workspace_id}/sources/{source_id}",
        json={"status": "paused"},
    )
    proposal_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/proposals",
        json={
            "proposal_type": "schema_proposal",
            "evidence_bundle_uri": "evidence://schema",
            "confidence": 0.6,
            "priority": "quality_critical",
            "blocking": True,
        },
    )
    task_id = proposal_response.json()["task"]["task_id"]
    client.post(
        f"/api/v1/workspaces/{workspace_id}/review_tasks/{task_id}/decision",
        json={"decision": "approve", "actor_id": "user:alice"},
    )
    client.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build-1/publish",
        json={"contracts_passed": True},
    )
    client.post(f"/api/v1/workspaces/{workspace_id}/builds/build-1/rollback")

    session = get_session_factory(_safe_settings().database_url)()
    try:
        events = session.execute(select(db_models.AuditEvent)).scalars().all()
        event_types = {event.event_type for event in events}
        assert "workspace.created" in event_types
        assert "source.created" in event_types
        assert "source.updated" in event_types
        assert "review.decision" in event_types
        assert "build.published" in event_types
        assert "build.rollback" in event_types
    finally:
        session.close()
