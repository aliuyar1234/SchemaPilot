from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import backend.gateway.executor as gateway_executor
from backend.control_plane.repository import create_target_db_profile, create_workspace
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import TargetDbState


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_target.db').as_posix()}",
        query_engine="target_db",
    )


def _auth_headers(token: str = "local-analyst-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gateway_target_db_engine_denies_when_no_target_db_is_configured(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "workspace_missing_target",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "engine_unavailable"


def test_gateway_target_db_engine_executes_sqlite_target_db(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_gateway_app(settings_factory=lambda: settings)
    sqlite_target = tmp_path / "target_serving.sqlite"
    with sqlite3.connect(sqlite_target.as_posix()) as connection:
        connection.execute("create table invoices (id integer primary key, amount real)")
        connection.execute("insert into invoices(id, amount) values (1, 10.5), (2, 20.0)")
        connection.commit()

    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Gateway Target Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="sqlite-serving",
            db_type="sqlite",
            mode="managed",
            connection={"database": sqlite_target.as_posix()},
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_1"
        state_row.current_schema_ref = "main"
        state_row.health_status = "healthy"
        session.commit()

    client = TestClient(app)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select id, amount from invoices order by id"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 2
    assert body["result"]["rows"] == [[1, 10.5], [2, 20.0]]
    assert body["provenance"]["target_db_id"] == str(profile["target_db_id"])
    assert body["provenance"]["target_schema_ref"] == "main"
    assert body["provenance"]["build_id"] == "build_1"


def test_gateway_target_db_sqlite_prefers_active_database_pointer(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_gateway_app(settings_factory=lambda: settings)
    sqlite_target = tmp_path / "target_active.sqlite"
    with sqlite3.connect(sqlite_target.as_posix()) as connection:
        connection.execute("create table invoices (id integer primary key, amount real)")
        connection.execute("insert into invoices(id, amount) values (1, 99.0)")
        connection.commit()
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Gateway Target Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="sqlite-serving",
            db_type="sqlite",
            mode="managed",
            connection={
                "database": (tmp_path / "missing.sqlite").as_posix(),
                "active_database": sqlite_target.as_posix(),
            },
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_2"
        state_row.current_schema_ref = "main"
        state_row.health_status = "healthy"
        session.commit()
    client = TestClient(app)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select id, amount from invoices"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["result"]["rows"] == [[1, 99.0]]


def test_gateway_target_db_engine_denies_postgres_without_reader_dsn(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_gateway_app(settings_factory=lambda: settings)
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Gateway Target Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="postgres-serving",
            db_type="postgres",
            mode="external",
            connection={"host": "db", "port": 5432, "database": "analytics"},
            credential_refs={"reader": "secret://local/r", "writer": "secret://local/w"},
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_1"
        state_row.current_schema_ref = "analytics"
        state_row.health_status = "healthy"
        session.commit()
    client = TestClient(app)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "engine_unavailable"


def test_gateway_target_db_engine_denies_mysql_without_reader_dsn(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_gateway_app(settings_factory=lambda: settings)
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Gateway Target Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="mysql-serving",
            db_type="mysql",
            mode="external",
            connection={"host": "db", "port": 3306, "database": "analytics"},
            credential_refs={"reader": "secret://local/r", "writer": "secret://local/w"},
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_1"
        state_row.current_schema_ref = "analytics"
        state_row.health_status = "healthy"
        session.commit()
    client = TestClient(app)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["details"]["reason"] == "engine_unavailable"


def test_gateway_target_db_engine_executes_postgres_via_mocked_driver(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    app = create_gateway_app(settings_factory=lambda: settings)
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Gateway Target Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="postgres-serving",
            db_type="postgres",
            mode="external",
            connection={
                "reader_dsn": "postgresql://readonly:secret@db.internal:5432/analytics",
                "schema": "analytics",
            },
            credential_refs={"reader": "secret://local/r", "writer": "secret://local/w"},
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_pg_1"
        state_row.current_schema_ref = "analytics"
        state_row.health_status = "healthy"
        session.commit()

    def _fake_postgres_query(  # type: ignore[no-untyped-def]
        *, dsn: str, query: str, timeout_ms: int, schema_ref: str | None, capped_rows: int
    ) -> tuple[list[dict[str, str]], list[list[object]]]:
        assert dsn.startswith("postgresql://")
        assert query.lower().startswith("select")
        assert timeout_ms > 0
        assert schema_ref == "analytics"
        return [{"name": "id", "type": "unknown"}], [[1]]

    monkeypatch.setattr(gateway_executor, "_execute_postgres_query", _fake_postgres_query)

    client = TestClient(app)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select id from invoices"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"] == [[1]]
    assert body["provenance"]["target_db_id"] == str(profile["target_db_id"])
    assert body["provenance"]["target_schema_ref"] == "analytics"
    assert body["provenance"]["build_id"] == "build_pg_1"


def test_gateway_target_db_engine_executes_mysql_via_mocked_driver(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    app = create_gateway_app(settings_factory=lambda: settings)
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Gateway Target Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="mysql-serving",
            db_type="mysql",
            mode="external",
            connection={"reader_dsn": "mysql+pymysql://readonly:secret@db.internal:3306/analytics"},
            credential_refs={"reader": "secret://local/r", "writer": "secret://local/w"},
        )
        state_row = session.get(TargetDbState, workspace_id)
        assert state_row is not None
        state_row.active_target_db_id = str(profile["target_db_id"])
        state_row.current_build_id = "build_mysql_1"
        state_row.current_schema_ref = "analytics"
        state_row.health_status = "healthy"
        session.commit()

    def _fake_mysql_query(  # type: ignore[no-untyped-def]
        *, dsn: str, query: str, timeout_ms: int, capped_rows: int
    ) -> tuple[list[dict[str, str]], list[list[object]]]:
        assert dsn.startswith("mysql")
        assert query.lower().startswith("select")
        assert timeout_ms > 0
        assert capped_rows >= 1
        return [{"name": "id", "type": "unknown"}], [[7]]

    monkeypatch.setattr(gateway_executor, "_execute_mysql_query", _fake_mysql_query)

    client = TestClient(app)
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select id from invoices"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["rows"] == [[7]]
    assert body["provenance"]["target_db_id"] == str(profile["target_db_id"])
    assert body["provenance"]["target_schema_ref"] == "analytics"
    assert body["provenance"]["build_id"] == "build_mysql_1"
