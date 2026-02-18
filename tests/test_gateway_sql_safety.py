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
        database_url="sqlite:///./runtime/test_gateway_sql_safety.db",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_denies_non_read_sql() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"language": "sql", "text": "drop table users"}},
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "sql_unsafe"


def test_gateway_denies_unsafe_sql_keyword_in_select_path() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one; attach database 'x' as y"},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "sql_unsafe"


def test_gateway_enforces_max_rows_constraints() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {
                "language": "sql",
                "text": (
                    "with recursive t(n) as (select 1 union all select n+1 "
                    "from t where n < 30) select n from t"
                ),
            },
            "constraints": {"max_rows": 3},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 200
    assert response.json()["result"]["row_count"] == 3


def test_gateway_denies_query_that_exceeds_timeout_budget() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {
                "language": "sql",
                "text": (
                    "with recursive t(n) as ("
                    "select 1 union all select n+1 from t where n < 10000000"
                    ") select n from t"
                ),
            },
            "constraints": {"timeout_ms": 1},
        },
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "query_timeout"
