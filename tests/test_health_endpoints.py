from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
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


def test_control_plane_health_endpoint() -> None:
    client = TestClient(create_app(settings_factory=_safe_settings))
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["service"] == "control_plane"


def test_gateway_health_endpoint() -> None:
    client = TestClient(create_gateway_app(settings_factory=_safe_settings))
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["service"] == "gateway"
