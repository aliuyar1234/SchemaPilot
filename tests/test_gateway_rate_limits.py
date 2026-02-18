from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url=f"sqlite:///{(tmp_path / 'gateway_rate_limits.db').as_posix()}",
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_denies_when_rate_limit_exceeded(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_MAX_REQUESTS_PER_MINUTE", "1")
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_MAX_CONCURRENT_PER_ACTOR", "4")
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))

    first = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"text": "select 1 as one"}},
        headers=_auth_headers("local-analyst-token"),
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"text": "select 1 as one"}},
        headers=_auth_headers("local-analyst-token"),
    )
    assert second.status_code == 403
    assert second.json()["error"]["details"]["reason"] == "rate_limit_exceeded"


def test_gateway_denies_when_concurrency_limit_exceeded(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_MAX_REQUESTS_PER_MINUTE", "10")
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_MAX_CONCURRENT_PER_ACTOR", "0")
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))

    response = client.post(
        "/api/v1/gateway/query",
        json={"workspace_id": "w1", "query": {"text": "select 1 as one"}},
        headers=_auth_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "concurrency_limit_exceeded"
