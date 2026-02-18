from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _oidc_settings() -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="127.0.0.1",
        auth_mode="oidc",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url="sqlite:///./runtime/test_gateway_oidc.db",
        oidc_required_issuer="https://issuer.example",
        oidc_required_audience="schemapilot-gateway",
    )


def _claims_header(claims: dict[str, object]) -> dict[str, str]:
    return {"x-schemapilot-oidc-claims": json.dumps(claims)}


def test_gateway_oidc_denies_missing_claims_header() -> None:
    client = TestClient(create_gateway_app(settings_factory=_oidc_settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"text": "select 1 as one"}},
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "missing_or_invalid_auth_token"


def test_gateway_oidc_allows_valid_claims_mapping() -> None:
    client = TestClient(create_gateway_app(settings_factory=_oidc_settings))
    claims = {
        "iss": "https://issuer.example",
        "aud": "schemapilot-gateway",
        "sub": "user:oidc_alice",
        "roles": ["analyst"],
        "attributes": {"region": "eu"},
    }
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"text": "select 'eu' as region, 'alice@example.com' as email"},
            "resource_attributes": {"region": "eu"},
        },
        headers=_claims_header(claims),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 1
    assert body["provenance"]["applied_masks"]["email"] == "partial_reveal"


def test_gateway_oidc_denies_issuer_mismatch() -> None:
    client = TestClient(create_gateway_app(settings_factory=_oidc_settings))
    claims = {
        "iss": "https://wrong-issuer.example",
        "aud": "schemapilot-gateway",
        "sub": "user:oidc_alice",
        "roles": ["analyst"],
        "attributes": {"region": "eu"},
    }
    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"text": "select 1 as one"}},
        headers=_claims_header(claims),
    )
    assert response.status_code == 403
