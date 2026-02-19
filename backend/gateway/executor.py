"""SQL execution helpers for gateway."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

import duckdb
from sqlalchemy import create_engine, text
from sqlalchemy.exc import NoSuchModuleError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.shared_domain.db import get_session_factory
from backend.shared_domain.gold_pointer import load_latest_gold_pointer
from backend.shared_domain.metadata_models import TargetDbProfile, TargetDbState


@dataclass(frozen=True)
class QueryResult:
    """Serialized SQL result set."""

    columns: list[dict[str, str]]
    rows: list[list[object]]
    row_count: int
    execution_metadata: dict[str, object] | None = None


FILTER_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
UNSAFE_SQL_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "attach",
    "detach",
    "copy",
    "export",
    "pragma",
    "vacuum",
    "create",
    "replace",
    "truncate",
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "glob",
    "install",
    "load",
    "httpfs",
}


class UnsafeSqlError(ValueError):
    """Raised when SQL violates gateway read-only safety rules."""


class QueryTimeoutError(ValueError):
    """Raised when SQL execution exceeds configured timeout budget."""


class QueryEngineUnavailableError(ValueError):
    """Raised when configured query engine is unavailable for safe execution."""


def _validate_filter_column(column: str) -> str:
    normalized = column.strip()
    if not FILTER_COLUMN_RE.match(normalized):
        raise ValueError(f"Invalid ABAC filter column: {column}")
    return normalized


def _normalized_max_rows(max_rows: int) -> int:
    if max_rows <= 0:
        return 1
    return min(max_rows, 5000)


def _validate_read_only_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        normalized = "select 1 as one"
    lowered = normalized.lower()
    if ";" in normalized:
        raise UnsafeSqlError("multiple_sql_statements_denied")
    if not (lowered.startswith("select") or lowered.startswith("with ")):
        raise UnsafeSqlError("only_select_or_cte_queries_allowed")
    for token in TOKEN_RE.findall(lowered):
        if token in UNSAFE_SQL_KEYWORDS:
            raise UnsafeSqlError(f"unsafe_sql_keyword_denied:{token}")
    return normalized


def execute_sql(
    sql: str,
    *,
    max_rows: int = 1000,
    row_filter: tuple[str, str] | None = None,
    timeout_ms: int = 5000,
    workspace_id: str | None = None,
    storage_root: str = "./runtime/storage",
    query_engine: str = "duckdb",
    trino_url: str = "http://trino:8080",
    trino_user: str = "schemapilot",
    trino_catalog: str = "memory",
    trino_schema: str = "default",
    metadata_database_url: str | None = None,
) -> QueryResult:
    """Execute SQL using an in-memory DuckDB engine for gateway behavior."""
    query = _validate_read_only_query(sql or "select 1 as one")
    capped_rows = _normalized_max_rows(max_rows)
    budget_ms = max(1, min(timeout_ms, 60_000))
    if budget_ms <= 1:
        raise QueryTimeoutError("query_timeout_exceeded")

    if query_engine == "trino":
        from backend.gateway.executor_trino import execute_sql_trino_with_metadata

        started_at = perf_counter()
        try:
            columns, trino_rows, metadata = execute_sql_trino_with_metadata(
                query=query,
                max_rows=capped_rows,
                timeout_ms=budget_ms,
                trino_url=trino_url,
                trino_user=trino_user,
                trino_catalog=trino_catalog,
                trino_schema=trino_schema,
            )
        except TimeoutError as exc:
            raise QueryTimeoutError("query_timeout_exceeded") from exc
        elapsed_ms = (perf_counter() - started_at) * 1000.0
        if elapsed_ms > float(budget_ms):
            raise QueryTimeoutError("query_timeout_exceeded")
        rows = _apply_optional_row_filter(
            columns=columns,
            rows=trino_rows,
            row_filter=row_filter,
            capped_rows=capped_rows,
        )
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_metadata=metadata,
        )
    if query_engine == "target_db":
        return _execute_sql_target_db(
            query=query,
            capped_rows=capped_rows,
            row_filter=row_filter,
            timeout_ms=budget_ms,
            workspace_id=workspace_id,
            metadata_database_url=metadata_database_url,
        )

    connection = duckdb.connect(database=":memory:")
    try:
        _prepare_published_gold_views(
            connection,
            workspace_id=workspace_id,
            storage_root=storage_root,
        )
        started_at = perf_counter()
        cursor = connection.execute(query)
        elapsed_ms = (perf_counter() - started_at) * 1000.0
        if elapsed_ms > float(budget_ms):
            raise QueryTimeoutError("query_timeout_exceeded")

        description = cursor.description or []
        columns = [
            {
                "name": str(item[0]),
                "type": str(item[1]) if len(item) > 1 and item[1] is not None else "unknown",
            }
            for item in description
        ]
        if row_filter is None:
            rows = [list(row) for row in cursor.fetchmany(capped_rows)]
        else:
            rows = _apply_optional_row_filter(
                columns=columns,
                rows=[list(row) for row in cursor.fetchall()],
                row_filter=row_filter,
                capped_rows=capped_rows,
            )
    finally:
        connection.close()
    return QueryResult(columns=columns, rows=rows, row_count=len(rows), execution_metadata={})


def _execute_sql_target_db(
    *,
    query: str,
    capped_rows: int,
    row_filter: tuple[str, str] | None,
    timeout_ms: int,
    workspace_id: str | None,
    metadata_database_url: str | None,
) -> QueryResult:
    if not workspace_id:
        raise QueryEngineUnavailableError("target_db_workspace_required")
    if not metadata_database_url:
        raise QueryEngineUnavailableError("target_db_metadata_unavailable")
    target_info = _load_active_target_db_info(
        metadata_database_url=metadata_database_url, workspace_id=workspace_id
    )
    if target_info is None:
        raise QueryEngineUnavailableError("target_db_not_configured")
    db_type = str(target_info["db_type"]).strip().lower()
    if db_type == "sqlite":
        return _execute_sql_target_db_sqlite(
            target_info=target_info,
            query=query,
            capped_rows=capped_rows,
            row_filter=row_filter,
            timeout_ms=timeout_ms,
        )
    if db_type == "postgres":
        return _execute_sql_target_db_postgres(
            target_info=target_info,
            query=query,
            capped_rows=capped_rows,
            row_filter=row_filter,
            timeout_ms=timeout_ms,
        )
    if db_type == "mysql":
        return _execute_sql_target_db_mysql(
            target_info=target_info,
            query=query,
            capped_rows=capped_rows,
            row_filter=row_filter,
            timeout_ms=timeout_ms,
        )
    raise QueryEngineUnavailableError(f"target_db_driver_unavailable:{target_info['db_type']}")


def _execute_sql_target_db_sqlite(
    *,
    target_info: dict[str, object],
    query: str,
    capped_rows: int,
    row_filter: tuple[str, str] | None,
    timeout_ms: int,
) -> QueryResult:
    connection_payload_raw = target_info.get("connection", {})
    connection_payload = (
        dict(connection_payload_raw)
        if isinstance(connection_payload_raw, dict)
        else {}
    )
    active_database_ref = str(connection_payload.get("active_database", "")).strip()
    database_ref = active_database_ref or str(connection_payload.get("database", "")).strip()
    if not database_ref:
        raise QueryEngineUnavailableError("target_db_sqlite_database_missing")
    normalized_path = Path(database_ref)
    if not normalized_path.exists():
        raise QueryEngineUnavailableError("target_db_sqlite_database_missing")
    sqlite_uri = f"file:{normalized_path.as_posix()}?mode=ro"
    started_at = perf_counter()
    connection = sqlite3.connect(sqlite_uri, uri=True, timeout=max(float(timeout_ms) / 1000.0, 1.0))
    try:
        cursor = connection.execute(query)
        elapsed_ms = (perf_counter() - started_at) * 1000.0
        if elapsed_ms > float(timeout_ms):
            raise QueryTimeoutError("query_timeout_exceeded")
        description = cursor.description or []
        columns = [
            {"name": str(item[0]), "type": "unknown"}
            for item in description
            if len(item) >= 1 and str(item[0]).strip()
        ]
        rows = (
            _apply_optional_row_filter(
                columns=columns,
                rows=[list(row) for row in cursor.fetchall()],
                row_filter=row_filter,
                capped_rows=capped_rows,
            )
            if row_filter is not None
            else [list(row) for row in cursor.fetchmany(capped_rows)]
        )
    except sqlite3.OperationalError as exc:
        raise QueryEngineUnavailableError("target_db_sqlite_unavailable") from exc
    finally:
        connection.close()
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_metadata={
            "engine": "target_db",
            "db_type": target_info["db_type"],
            "target_db_id": target_info["target_db_id"],
            "current_build_id": target_info["current_build_id"],
            "current_schema_ref": target_info["current_schema_ref"],
        },
    )


def _execute_sql_target_db_postgres(
    *,
    target_info: dict[str, object],
    query: str,
    capped_rows: int,
    row_filter: tuple[str, str] | None,
    timeout_ms: int,
) -> QueryResult:
    connection_payload_raw = target_info.get("connection", {})
    connection_payload = (
        dict(connection_payload_raw)
        if isinstance(connection_payload_raw, dict)
        else {}
    )
    reader_dsn = _resolve_postgres_reader_dsn(connection_payload)
    started_at = perf_counter()
    try:
        columns, rows = _execute_postgres_query(
            dsn=reader_dsn,
            query=query,
            timeout_ms=timeout_ms,
            schema_ref=str(target_info.get("current_schema_ref", "")).strip() or None,
            capped_rows=capped_rows,
        )
    except QueryTimeoutError:
        raise
    except ValueError as exc:
        raise QueryEngineUnavailableError(str(exc)) from exc
    elapsed_ms = (perf_counter() - started_at) * 1000.0
    if elapsed_ms > float(timeout_ms):
        raise QueryTimeoutError("query_timeout_exceeded")
    filtered_rows = (
        _apply_optional_row_filter(
            columns=columns,
            rows=rows,
            row_filter=row_filter,
            capped_rows=capped_rows,
        )
        if row_filter is not None
        else rows[:capped_rows]
    )
    return QueryResult(
        columns=columns,
        rows=filtered_rows,
        row_count=len(filtered_rows),
        execution_metadata={
            "engine": "target_db",
            "db_type": "postgres",
            "target_db_id": target_info["target_db_id"],
            "current_build_id": target_info["current_build_id"],
            "current_schema_ref": target_info["current_schema_ref"],
        },
    )


def _execute_sql_target_db_mysql(
    *,
    target_info: dict[str, object],
    query: str,
    capped_rows: int,
    row_filter: tuple[str, str] | None,
    timeout_ms: int,
) -> QueryResult:
    connection_payload_raw = target_info.get("connection", {})
    connection_payload = (
        dict(connection_payload_raw)
        if isinstance(connection_payload_raw, dict)
        else {}
    )
    reader_dsn = _resolve_mysql_reader_dsn(connection_payload)
    started_at = perf_counter()
    try:
        columns, rows = _execute_mysql_query(
            dsn=reader_dsn,
            query=query,
            timeout_ms=timeout_ms,
            capped_rows=capped_rows,
        )
    except QueryTimeoutError:
        raise
    except ValueError as exc:
        raise QueryEngineUnavailableError(str(exc)) from exc
    elapsed_ms = (perf_counter() - started_at) * 1000.0
    if elapsed_ms > float(timeout_ms):
        raise QueryTimeoutError("query_timeout_exceeded")
    filtered_rows = (
        _apply_optional_row_filter(
            columns=columns,
            rows=rows,
            row_filter=row_filter,
            capped_rows=capped_rows,
        )
        if row_filter is not None
        else rows[:capped_rows]
    )
    return QueryResult(
        columns=columns,
        rows=filtered_rows,
        row_count=len(filtered_rows),
        execution_metadata={
            "engine": "target_db",
            "db_type": "mysql",
            "target_db_id": target_info["target_db_id"],
            "current_build_id": target_info["current_build_id"],
            "current_schema_ref": target_info["current_schema_ref"],
        },
    )


def _resolve_postgres_reader_dsn(connection_payload: dict[str, object]) -> str:
    reader_dsn = str(connection_payload.get("reader_dsn", "")).strip()
    if not reader_dsn:
        raise QueryEngineUnavailableError("target_db_postgres_reader_dsn_missing")
    parsed = urlparse(reader_dsn)
    if not parsed.scheme.startswith("postgresql"):
        raise QueryEngineUnavailableError("target_db_postgres_reader_dsn_invalid")
    return reader_dsn


def _resolve_mysql_reader_dsn(connection_payload: dict[str, object]) -> str:
    reader_dsn = str(connection_payload.get("reader_dsn", "")).strip()
    if not reader_dsn:
        raise QueryEngineUnavailableError("target_db_mysql_reader_dsn_missing")
    parsed = urlparse(reader_dsn)
    if not parsed.scheme.startswith("mysql"):
        raise QueryEngineUnavailableError("target_db_mysql_reader_dsn_invalid")
    return reader_dsn


def _execute_postgres_query(
    *,
    dsn: str,
    query: str,
    timeout_ms: int,
    schema_ref: str | None,
    capped_rows: int,
) -> tuple[list[dict[str, str]], list[list[object]]]:
    safe_schema = _safe_identifier(schema_ref) if schema_ref else None
    try:
        engine = create_engine(dsn, future=True)
    except (NoSuchModuleError, ModuleNotFoundError) as exc:
        raise ValueError("target_db_postgres_driver_unavailable") from exc
    try:
        with engine.connect() as connection:
            if safe_schema:
                connection.exec_driver_sql(
                    f"set search_path to {safe_schema}"  # nosec B608 - identifier normalized by _safe_identifier
                )
            connection.execute(
                text("set statement_timeout = :timeout_ms"),
                {"timeout_ms": timeout_ms},
            )
            result = connection.execute(text(query))
            columns = [{"name": str(name), "type": "unknown"} for name in result.keys()]
            rows = [list(row) for row in result.fetchmany(capped_rows)]
            return columns, rows
    except SQLAlchemyError as exc:
        message = str(exc).lower()
        if "statement timeout" in message or "query canceled" in message:
            raise QueryTimeoutError("query_timeout_exceeded") from exc
        raise ValueError("target_db_postgres_unavailable") from exc
    finally:
        engine.dispose()


def _execute_mysql_query(
    *,
    dsn: str,
    query: str,
    timeout_ms: int,
    capped_rows: int,
) -> tuple[list[dict[str, str]], list[list[object]]]:
    try:
        engine = create_engine(dsn, future=True)
    except (NoSuchModuleError, ModuleNotFoundError) as exc:
        raise ValueError("target_db_mysql_driver_unavailable") from exc
    try:
        with engine.connect() as connection:
            # Best-effort server timeout guard for MySQL-compatible engines.
            connection.execute(
                text("set session max_execution_time = :timeout_ms"),
                {"timeout_ms": timeout_ms},
            )
            result = connection.execute(text(query))
            columns = [{"name": str(name), "type": "unknown"} for name in result.keys()]
            rows = [list(row) for row in result.fetchmany(capped_rows)]
            return columns, rows
    except SQLAlchemyError as exc:
        message = str(exc).lower()
        if "max execution time exceeded" in message or "query execution was interrupted" in message:
            raise QueryTimeoutError("query_timeout_exceeded") from exc
        raise ValueError("target_db_mysql_unavailable") from exc
    finally:
        engine.dispose()


def _apply_optional_row_filter(
    *,
    columns: list[dict[str, str]],
    rows: list[list[object]],
    row_filter: tuple[str, str] | None,
    capped_rows: int,
) -> list[list[object]]:
    if row_filter is None:
        return rows[:capped_rows]
    filter_column, filter_value = row_filter
    normalized_column = _validate_filter_column(filter_column)
    column_names = [column["name"] for column in columns]
    try:
        filter_idx = column_names.index(normalized_column)
    except ValueError:
        return []
    filtered: list[list[object]] = []
    for row in rows:
        if filter_idx >= len(row):
            continue
        if str(row[filter_idx]) == str(filter_value):
            filtered.append(list(row))
        if len(filtered) >= capped_rows:
            break
    return filtered


def _prepare_published_gold_views(
    connection: duckdb.DuckDBPyConnection,
    *,
    workspace_id: str | None,
    storage_root: str,
) -> None:
    if not workspace_id:
        return
    pointer = load_latest_gold_pointer(workspace_id=workspace_id, storage_root=storage_root)
    if pointer is None:
        return
    model_name = str(pointer.get("model_name", "")).strip()
    snapshot_id = str(pointer.get("snapshot_id", "")).strip()
    if not model_name or not snapshot_id:
        return
    data_path = (
        Path(storage_root)
        / "gold"
        / workspace_id
        / model_name
        / "snapshots"
        / snapshot_id
        / "metrics.json"
    )
    if not data_path.exists():
        return
    safe_model_name = _safe_identifier(model_name)
    safe_data_path = data_path.as_posix().replace("'", "''")
    connection.execute("create schema if not exists gold")
    connection.execute(
        f"create or replace view gold.fact_metrics as "
        f"select * from read_json_auto('{safe_data_path}')"  # nosec B608 - path is server-side and single-quoted escaped
    )
    connection.execute(
        f"create or replace view gold.{safe_model_name} as select * from gold.fact_metrics"  # nosec B608 - identifier is normalized by _safe_identifier
    )


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not normalized:
        return "model"
    if normalized[0].isdigit():
        return f"_{normalized}"
    return normalized


def _load_active_target_db_info(
    *, metadata_database_url: str, workspace_id: str
) -> dict[str, object] | None:
    session_factory = get_session_factory(metadata_database_url)
    with session_factory() as session:
        state = session.get(TargetDbState, workspace_id)
        if state is None or not state.active_target_db_id:
            return None
        profile = _load_target_db_profile(
            session=session,
            workspace_id=workspace_id,
            target_db_id=state.active_target_db_id,
        )
        if profile is None:
            return None
        return {
            "target_db_id": profile.target_db_id,
            "db_type": str(profile.db_type),
            "connection": dict(profile.connection_json),
            "current_build_id": state.current_build_id,
            "current_schema_ref": state.current_schema_ref,
        }


def _load_target_db_profile(
    *, session: Session, workspace_id: str, target_db_id: str
) -> TargetDbProfile | None:
    profile = session.get(TargetDbProfile, target_db_id)
    if profile is None:
        return None
    if profile.workspace_id != workspace_id:
        return None
    return profile
