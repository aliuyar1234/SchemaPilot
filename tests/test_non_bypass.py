from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_non_bypass.db",
    )


def test_control_plane_has_no_gateway_query_endpoint() -> None:
    control = TestClient(create_app(settings_factory=_settings))
    response = control.post("/api/v1/gateway/query", json={})
    assert response.status_code == 404


def test_gateway_path_is_available_for_query_access() -> None:
    gateway = TestClient(create_gateway_app(settings_factory=_settings))
    response = gateway.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "actor": {"actor_id": "user:bob", "actor_type": "human", "roles": ["analyst"]},
            "query": {"language": "sql", "text": "select 1 as one"},
        },
    )
    assert response.status_code == 200
