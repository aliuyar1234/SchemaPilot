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
        database_url="sqlite:///./runtime/test_gateway_simulation.db",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_policy_simulation_allows_steward_role() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/policy/simulate",
        headers=_headers("local-data-steward-token"),
        json={
            "workspace_id": "w1",
            "action": "query",
            "actor": {"actor_type": "human", "roles": ["analyst"], "attributes": {}},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] in {"allow", "deny"}
    assert "policy_decision_id" in body


def test_policy_simulation_denies_non_steward_role() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/policy/simulate",
        headers=_headers("local-analyst-token"),
        json={
            "workspace_id": "w1",
            "action": "query",
            "actor": {"actor_type": "human", "roles": ["analyst"], "attributes": {}},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "simulation_forbidden"
