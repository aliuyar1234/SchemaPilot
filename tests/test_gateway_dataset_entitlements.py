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
        database_url="sqlite:///./runtime/test_gateway_dataset_entitlements.db",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_denies_ai_query_without_dataset_context() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"language": "sql", "text": "select 1 as one"}},
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "missing_dataset_context"


def test_gateway_denies_ai_query_for_unentitled_dataset() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-forbidden"},
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "dataset_not_allowed"


def test_gateway_allows_ai_query_for_entitled_dataset() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers("local-ai-reader-token"),
    )
    assert response.status_code == 200
    assert response.json()["result"]["row_count"] == 1

