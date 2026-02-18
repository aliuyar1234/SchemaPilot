from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.tracing import start_trace


def test_start_trace_disabled_returns_correlation_id() -> None:
    trace = start_trace(
        service_name="schemapilot-test",
        operation="unit.test",
        correlation_id="req-123",
        enabled=False,
    )
    assert trace.trace_id == "req-123"
    assert trace.enabled is False


def test_gateway_and_control_plane_emit_trace_headers_when_enabled(tmp_path) -> None:
    settings = Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'trace_headers.db').as_posix()}",
        tracing_enabled=True,
        tracing_service_name="schemapilot-test",
    )
    gateway_client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    gateway_response = gateway_client.get("/api/v1/health")
    assert gateway_response.status_code == 200
    assert gateway_response.headers.get("x-trace-id")

    cp_client = TestClient(create_app(settings_factory=lambda: settings))
    cp_response = cp_client.get("/api/v1/health")
    assert cp_response.status_code == 200
    assert cp_response.headers.get("x-trace-id")
