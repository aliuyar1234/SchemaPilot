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
        database_url="sqlite:///./runtime/test_gateway_retrieve.db",
    )


def test_gateway_retrieval_for_allowlisted_ai_identity() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "actor": {
                "actor_id": "agent:a",
                "actor_type": "ai",
                "roles": ["ai_agent"],
                "attributes": {"allowlisted": True, "allowed_dataset_ids": ["dataset-1"]},
            },
            "query_text": "invoice",
            "corpus": [
                {
                    "artifact_id": "a1",
                    "dataset_id": "dataset-1",
                    "text": "invoice for customer c-1",
                    "citation": "artifact:a1",
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["provenance"]["datasets_used"] == ["dataset-1"]
    assert body["provenance"]["citations"] == ["artifact:a1"]


def test_gateway_retrieval_denies_non_allowlisted_ai() -> None:
    client = TestClient(create_gateway_app(settings_factory=_settings))
    response = client.post(
        "/api/v1/gateway/retrieve",
        json={
            "workspace_id": "w1",
            "actor": {
                "actor_id": "agent:a",
                "actor_type": "ai",
                "roles": ["ai_agent"],
                "attributes": {"allowlisted": False, "allowed_dataset_ids": ["dataset-1"]},
            },
            "query_text": "invoice",
            "corpus": [],
        },
    )
    assert response.status_code == 403
