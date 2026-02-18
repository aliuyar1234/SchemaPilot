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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_denies_ai_actor_by_default() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "actor": {
                "actor_id": "agent:spoof",
                "actor_type": "human",
                "roles": ["platform_admin"],
            },
            "query": {"language": "sql", "text": "select 1"},
        },
        headers=_auth_headers("local-ai-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "ai_tool_deny_by_default"


def test_gateway_requires_authenticated_token_context() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "actor": {
                "actor_id": "user:spoof",
                "actor_type": "human",
                "roles": ["platform_admin"],
            },
            "query": {"language": "sql", "text": "select 1"},
        },
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "missing_or_invalid_auth_token"


def test_gateway_allows_analyst_role_from_authenticated_context() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "actor": {
                "actor_id": "user:spoof",
                "actor_type": "human",
                "roles": ["platform_admin"],
            },
            "query": {"language": "sql", "text": "select 1"},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 200
    assert "provenance" in response.json()


def test_gateway_enforces_abac_row_filter_and_masking() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {
                "language": "sql",
                "text": (
                    "select 'eu' as region, 'alice@example.com' as email "
                    "union all select 'us', 'bob@example.com'"
                ),
            },
            "resource_attributes": {"region": "eu"},
        },
        headers=_auth_headers("local-region-analyst-token"),
    )
    assert response.status_code == 200
    rows = response.json()["result"]["rows"]
    assert len(rows) == 1
    assert rows[0][0] == "eu"
    assert rows[0][1] != "alice@example.com"


def test_gateway_applies_abac_filter_to_non_matching_result_sets() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"region": "eu"},
        },
        headers=_auth_headers("local-region-analyst-token"),
    )
    assert response.status_code == 200
    assert response.json()["result"]["row_count"] == 0
