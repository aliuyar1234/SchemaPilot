from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.observability import log_structured_event


def _gateway_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_observability_gateway.db",
    )


def _control_settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_observability_control.db",
    )


def test_gateway_metrics_endpoint_exposes_required_signals() -> None:
    client = TestClient(create_gateway_app(settings_factory=_gateway_settings))

    client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w-obs",
            "actor": {"actor_id": "agent:a", "actor_type": "ai", "roles": ["ai_agent"]},
            "query": {"language": "sql", "text": "select 1"},
        },
    )
    client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w-obs",
            "actor": {"actor_id": "user:alice", "actor_type": "human", "roles": ["analyst"]},
            "query": {"language": "sql", "text": "select 1"},
        },
    )
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    text = response.text
    assert "schemapilot_query_latency_ms" in text
    assert "schemapilot_policy_denials_total" in text
    assert "schemapilot_cost_bytes_scanned_total" in text


def test_control_plane_metrics_tracks_review_queue_backlog() -> None:
    client = TestClient(create_app(settings_factory=_control_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Observability", "profile": "starter", "security_baseline": "standard"},
    ).json()
    workspace_id = workspace["workspace_id"]
    client.post(
        f"/api/v1/workspaces/{workspace_id}/proposals",
        json={
            "proposal_type": "pii_tag_proposal",
            "evidence_bundle_uri": "evidence://obs",
            "confidence": 0.4,
            "priority": "security_critical",
            "blocking": True,
        },
    )
    list_response = client.get(f"/api/v1/workspaces/{workspace_id}/review_tasks")
    assert list_response.status_code == 200
    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert "schemapilot_review_queue_backlog_total" in metrics.text


def test_structured_logging_redacts_secret_like_values(caplog) -> None:
    caplog.set_level(logging.INFO, logger="schemapilot")
    log_structured_event(
        level="info",
        msg="token received",
        service="gateway",
        correlation_id="01HTESTCORRELATION",
        extra={"token": "sk-abc123xyz456"},
    )
    assert "[REDACTED]" in caplog.text
