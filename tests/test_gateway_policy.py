from __future__ import annotations

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _safe_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test.db",
    )


def test_gateway_denies_ai_actor_by_default() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "actor": {
                "actor_id": "agent:test",
                "actor_type": "ai",
                "roles": ["ai_agent"],
            },
            "query": {"language": "sql", "text": "select 1"},
        },
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"


def test_gateway_allows_analyst_role() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "actor": {
                "actor_id": "user:alice",
                "actor_type": "human",
                "roles": ["analyst"],
            },
            "query": {"language": "sql", "text": "select 1"},
        },
    )
    assert response.status_code == 200
    assert "provenance" in response.json()
