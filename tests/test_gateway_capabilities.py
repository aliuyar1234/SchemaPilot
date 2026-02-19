from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory, prepare_database
from backend.shared_domain.errors import StartupConfigurationError
from backend.shared_domain.metadata_models import GovernancePolicy, Workspace


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_capabilities.db').as_posix()}",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _ensure_workspace(settings: Settings, workspace_id: str) -> None:
    prepare_database(settings)
    session_factory = get_session_factory(settings.database_url)
    session: Session = session_factory()
    try:
        existing = session.get(Workspace, workspace_id)
        if existing is None:
            session.add(
                Workspace(
                    workspace_id=workspace_id,
                    name="Gateway WS",
                    profile="team",
                    security_baseline="strict",
                )
            )
            session.commit()
    finally:
        session.close()


def test_pgwire_endpoint_is_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SCHEMAPILOT_GATEWAY_PGWIRE_ENABLED", raising=False)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/pgwire/query",
        json={"workspace_id": "ws1", "sql": "select 1"},
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "module_disabled"


def test_pgwire_endpoint_enforces_select_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_PGWIRE_ENABLED", "true")
    settings = _settings(tmp_path)
    _ensure_workspace(settings, "ws1")
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    denied = client.post(
        "/api/v1/gateway/pgwire/query",
        json={"workspace_id": "ws1", "sql": "delete from x"},
        headers=_headers("local-analyst-token"),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["details"]["reason"] == "pgwire_select_only"


def test_query_explain_uses_role_budget_policy(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _ensure_workspace(settings, "ws1")
    session = get_session_factory(settings.database_url)()
    try:
        session.add(
            GovernancePolicy(
                policy_id="budget-ws1",
                workspace_id="ws1",
                policy_type="query_budget",
                definition_ref='{"default_bytes":1000,"per_role_bytes":{"analyst":10}}',
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query-explain",
        json={"workspace_id": "ws1", "query_text": "select 1", "estimated_rows": 50},
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query_budget_source"] == "policy_per_role"
    assert body["query_budget_bytes"] == 10
    assert body["result"] in {"allow", "deny"}


def test_tokenization_endpoint_requires_module_enable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SCHEMAPILOT_TOKENIZATION_ENABLED", raising=False)
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.post(
        "/api/v1/gateway/tokenize",
        json={"workspace_id": "ws1", "value": "secret@example.com"},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INTEGRATION_DISABLED"


def test_tokenization_roundtrip_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_TOKENIZATION_ENABLED", "true")
    settings = _settings(tmp_path)
    _ensure_workspace(settings, "ws1")
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    tokenized = client.post(
        "/api/v1/gateway/tokenize",
        json={"workspace_id": "ws1", "value": "secret@example.com"},
        headers=_headers("local-data-steward-token"),
    )
    assert tokenized.status_code == 200
    token = tokenized.json()["token"]
    detokenized = client.post(
        "/api/v1/gateway/detokenize",
        json={"workspace_id": "ws1", "token": token},
        headers=_headers("local-platform-admin-token"),
    )
    assert detokenized.status_code == 200
    assert detokenized.json()["value"] == "secret@example.com"


def test_sample_endpoint_returns_bounded_rows(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _ensure_workspace(settings, "ws1")
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/sample",
        json={"workspace_id": "ws1", "query_text": "select 1 as one", "max_rows": 1000},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sample"]["max_rows"] == 25


def test_gateway_ha_requires_redis_url_when_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_HA_ENABLED", "true")
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_REDIS_REQUIRED", "true")
    monkeypatch.delenv("SCHEMAPILOT_GATEWAY_REDIS_URL", raising=False)
    with pytest.raises(StartupConfigurationError):
        create_gateway_app(settings_factory=lambda: _settings(tmp_path))


def test_gateway_ha_status_endpoint_reports_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_HA_ENABLED", "true")
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_REDIS_REQUIRED", "true")
    monkeypatch.setenv("SCHEMAPILOT_GATEWAY_REDIS_URL", "redis://localhost:6379/0")
    client = TestClient(create_gateway_app(settings_factory=lambda: _settings(tmp_path)))
    response = client.get("/api/v1/gateway/ha/status")
    assert response.status_code == 200
    body = response.json()
    assert body["gateway_ha_enabled"] is True
    assert body["redis_required"] is True
    assert body["redis_configured"] is True
