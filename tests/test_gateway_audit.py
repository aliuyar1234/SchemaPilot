from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.gateway.app import create_gateway_app
from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory


def _safe_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_gateway_audit.db",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_query_writes_audit_and_access_decision() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "workspace-a",
            "query": {"language": "sql", "text": "select 1"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 200

    session = get_session_factory(_safe_settings().database_url)()
    try:
        events = session.execute(select(AuditEvent)).scalars().all()
        decisions = session.execute(select(AccessDecision)).scalars().all()
        assert len(events) >= 1
        assert len(decisions) >= 1
        assert any(event.event_type == "gateway.query" for event in events)
        assert any("dataset-1" in str(decision.resources_json) for decision in decisions)
    finally:
        session.close()
