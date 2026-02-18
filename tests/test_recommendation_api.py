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


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-platform-admin-token"}


def test_recommendation_endpoint_returns_report_fields() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "rec", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/recommendations",
        json={"intent": {"strict_security": True, "needs_documents": True}},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert "ranked_templates" in body
    assert "hard_constraint_gates" in body
    assert "confidence" in body


def test_recommendation_endpoint_surfaces_missing_evidence_and_approval() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "rec-2", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/recommendations",
        json={
            "intent": {
                "strict_security": True,
                "needs_documents": True,
                "confidence_signal": 0.2,
                "evidence_completeness": 0.2,
            }
        },
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_required"] is True
    assert "confidence_below_threshold" in body["approval_reasons"]
    assert "query_workload_evidence" in body["missing_evidence"]
    assert "deployment_constraints_confirmation" in body["missing_evidence"]


def test_recommendation_get_not_found_uses_error_contract() -> None:
    client = TestClient(create_app(settings_factory=_settings))
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "rec-3", "profile": "starter", "security_baseline": "standard"},
        headers=_admin_headers(),
    ).json()
    workspace_id = workspace["workspace_id"]
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/recommendations/missing-report",
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"]["report_id"] == "missing-report"
