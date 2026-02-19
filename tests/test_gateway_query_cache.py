from __future__ import annotations

from fastapi.testclient import TestClient

import backend.gateway.app as gateway_app
from backend.control_plane.repository import create_target_db_profile, create_workspace
from backend.gateway.executor import QueryResult
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import TargetDbState


def _settings(tmp_path, *, cache_enabled: bool, query_engine: str = "duckdb") -> Settings:
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
        query_engine=query_engine,
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


def test_gateway_target_db_cache_key_tracks_target_build_id(tmp_path, monkeypatch) -> None:
    calls = {"count": 0}

    def fake_execute_sql(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        calls["count"] += 1
        return QueryResult(
            columns=[{"name": "one", "type": "INTEGER"}],
            rows=[[1]],
            row_count=1,
            execution_metadata={
                "engine": "target_db",
                "db_type": "sqlite",
                "target_db_id": "tdb_1",
                "current_build_id": kwargs.get("workspace_id", "build_unknown"),
                "current_schema_ref": "main",
            },
        )

    monkeypatch.setattr(gateway_app, "execute_sql", fake_execute_sql)
    settings = _settings(tmp_path, cache_enabled=True, query_engine="target_db")
    _ = gateway_app.create_gateway_app(settings_factory=lambda: settings)
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Cache Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        target = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="sqlite",
            mode="managed",
            connection={"database": (tmp_path / "serving.sqlite").as_posix()},
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(target["target_db_id"])
        state_row.current_build_id = "build_a"
        state_row.current_schema_ref = "main"
        state_row.health_status = "healthy"
        session.commit()

    client = TestClient(gateway_app.create_gateway_app(settings_factory=lambda: settings))
    payload = {
        "workspace_id": workspace_id,
        "query": {"language": "sql", "text": "select 1 as one"},
        "resource_attributes": {"dataset_id": "dataset-1"},
    }
    headers = {"Authorization": "Bearer local-analyst-token"}
    first = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    second = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1

    with session_factory() as session:
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.current_build_id = "build_b"
        session.commit()

    third = client.post("/api/v1/gateway/query", json=payload, headers=headers)
    assert third.status_code == 200
    assert calls["count"] == 2
