from __future__ import annotations

from fastapi.testclient import TestClient

import backend.gateway.app as gateway_app
from backend.gateway.executor import QueryResult
from backend.shared_domain.config import Settings


def _settings(tmp_path, *, cache_enabled: bool) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_cache.db').as_posix()}",
        gateway_query_cache_enabled=cache_enabled,
        gateway_query_cache_ttl_seconds=60,
        gateway_query_cache_max_entries=64,
    )


def test_gateway_query_cache_hits_when_enabled(tmp_path, monkeypatch) -> None:
    calls = {"count": 0}

    def fake_execute_sql(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        calls["count"] += 1
        return QueryResult(
            columns=[{"name": "one", "type": "INTEGER"}],
            rows=[[1]],
            row_count=1,
        )

    monkeypatch.setattr(gateway_app, "execute_sql", fake_execute_sql)
    client = TestClient(create_gateway_app_with_settings(tmp_path, cache_enabled=True))
    payload = {
        "workspace_id": "w1",
        "query": {"language": "sql", "text": "select 1 as one"},
        "resource_attributes": {"dataset_id": "dataset-1"},
    }
    headers = {"Authorization": "Bearer local-analyst-token"}
    first = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    second = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1


def test_gateway_query_cache_miss_when_disabled(tmp_path, monkeypatch) -> None:
    calls = {"count": 0}

    def fake_execute_sql(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        calls["count"] += 1
        return QueryResult(
            columns=[{"name": "one", "type": "INTEGER"}],
            rows=[[1]],
            row_count=1,
        )

    monkeypatch.setattr(gateway_app, "execute_sql", fake_execute_sql)
    client = TestClient(create_gateway_app_with_settings(tmp_path, cache_enabled=False))
    payload = {
        "workspace_id": "w1",
        "query": {"language": "sql", "text": "select 1 as one"},
        "resource_attributes": {"dataset_id": "dataset-1"},
    }
    headers = {"Authorization": "Bearer local-analyst-token"}
    first = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    second = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 2


def create_gateway_app_with_settings(tmp_path, *, cache_enabled: bool):
    settings = _settings(tmp_path, cache_enabled=cache_enabled)
    return gateway_app.create_gateway_app(settings_factory=lambda: settings)

