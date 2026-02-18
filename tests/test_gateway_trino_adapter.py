from __future__ import annotations

from fastapi.testclient import TestClient

from backend.gateway import executor_trino
from backend.gateway.app import create_gateway_app
from backend.gateway.executor import UnsafeSqlError, execute_sql
from backend.shared_domain.config import Settings


def test_execute_sql_uses_trino_adapter_with_pagination(monkeypatch) -> None:
    responses = iter(
        [
            {
                "columns": [{"name": "value", "type": "bigint"}],
                "data": [[1]],
                "nextUri": "http://trino.local/next",
            },
            {
                "data": [[2]],
                "nextUri": "",
            },
        ]
    )

    def fake_request_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return next(responses)

    monkeypatch.setattr(executor_trino, "_request_json", fake_request_json)
    result = execute_sql(
        "select value from demo",
        query_engine="trino",
        max_rows=10,
        timeout_ms=5000,
    )
    assert result.row_count == 2
    assert result.columns[0]["name"] == "value"
    assert result.rows == [[1], [2]]


def test_trino_path_still_denies_unsafe_sql_before_remote_execution(monkeypatch) -> None:
    called = {"value": False}

    def fake_request_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        called["value"] = True
        return {}

    monkeypatch.setattr(executor_trino, "_request_json", fake_request_json)
    try:
        execute_sql(
            "select * from read_csv_auto('secret.csv')",
            query_engine="trino",
            max_rows=10,
            timeout_ms=5000,
        )
    except UnsafeSqlError:
        pass
    else:
        raise AssertionError("Expected UnsafeSqlError for unsafe SQL")
    assert called["value"] is False


def test_gateway_query_can_use_trino_engine_path(monkeypatch, tmp_path) -> None:
    def fake_request_json(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return {
            "columns": [{"name": "one", "type": "bigint"}],
            "data": [[1]],
            "nextUri": "",
        }

    monkeypatch.setattr(executor_trino, "_request_json", fake_request_json)
    settings = Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'gateway_trino.db').as_posix()}",
        query_engine="trino",
    )
    client = TestClient(create_gateway_app(settings_factory=lambda: settings))
    response = client.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": "w1",
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers={"Authorization": "Bearer local-analyst-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["row_count"] == 1
    assert body["result"]["rows"] == [[1]]


def test_execute_sql_trino_retries_transient_request_errors(monkeypatch) -> None:
    attempts = {"count": 0}

    def flaky_request_json(*, method: str, url: str, payload, headers, timeout_seconds):  # type: ignore[no-untyped-def]
        _ = (method, url, payload, headers, timeout_seconds)
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("temporary timeout")
        return {"columns": [{"name": "value", "type": "bigint"}], "data": [[1]], "nextUri": ""}

    monkeypatch.setattr(executor_trino, "_request_json", flaky_request_json)
    columns, rows = executor_trino.execute_sql_trino(
        query="select 1 as value",
        max_rows=10,
        timeout_ms=3000,
        trino_url="http://trino.local",
        trino_user="user",
        trino_catalog="memory",
        trino_schema="default",
        max_retries=1,
    )
    assert attempts["count"] == 2
    assert columns[0]["name"] == "value"
    assert rows == [[1]]


def test_execute_sql_trino_cancels_query_on_timeout(monkeypatch) -> None:
    responses = iter(
        [
            {
                "id": "query_123",
                "columns": [{"name": "value", "type": "bigint"}],
                "data": [[1]],
                "nextUri": "http://trino.local/next",
            }
        ]
    )
    cancelled = {"called": False, "query_id": ""}

    def fake_request_json(*, method: str, url: str, payload, headers, timeout_seconds):  # type: ignore[no-untyped-def]
        _ = (payload, headers, timeout_seconds)
        if method == "DELETE":
            cancelled["called"] = True
            cancelled["query_id"] = url.rsplit("/", 1)[-1]
            return {}
        if method == "GET":
            raise TimeoutError("forced page timeout")
        return next(responses)

    monkeypatch.setattr(executor_trino, "_request_json", fake_request_json)
    try:
        executor_trino.execute_sql_trino(
            query="select value from demo",
            max_rows=10,
            timeout_ms=1,
            trino_url="http://trino.local",
            trino_user="user",
            trino_catalog="memory",
            trino_schema="default",
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("Expected TimeoutError")
    assert cancelled["called"] is True
    assert cancelled["query_id"] == "query_123"
