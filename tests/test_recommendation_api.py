from __future__ import annotations

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings


def _settings() -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_recommendation.db",
    )


def test_recommendation_endpoint_returns_report_fields() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "rec", "profile": "starter", "security_baseline": "standard"},
    ).json()
    workspace_id = workspace["workspace_id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/recommendations",
        json={"intent": {"strict_security": True, "needs_documents": True}},
    )
    assert response.status_code == 200
    body = response.json()
    assert "ranked_templates" in body
    assert "hard_constraint_gates" in body
    assert "confidence" in body
