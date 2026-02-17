from __future__ import annotations

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_gateway_query.db",
    )


def test_gateway_executes_sql_and_returns_provenance() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "actor": {"actor_id": "user:a", "actor_type": "human", "roles": ["analyst"]},
            "query": {"language": "sql", "text": "select 1 as one"},
            "constraints": {"max_rows": 10},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 1
    assert "policy_decision_id" in body["provenance"]
