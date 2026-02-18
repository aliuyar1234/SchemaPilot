"""SQL execution helpers for gateway."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import duckdb

from backend.shared_domain.gold_pointer import load_latest_gold_pointer


@dataclass(frozen=True)
class QueryResult:
    """Serialized SQL result set."""

    columns: list[dict[str, str]]
    rows: list[list[object]]
    row_count: int


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
) -> QueryResult:
    """Execute SQL using an in-memory DuckDB engine for gateway behavior."""
    query = _validate_read_only_query(sql or "select 1 as one")
    capped_rows = _normalized_max_rows(max_rows)
    budget_ms = max(1, min(timeout_ms, 60_000))
    if budget_ms <= 1:
        raise QueryTimeoutError("query_timeout_exceeded")

    if query_engine == "trino":
        from backend.gateway.executor_trino import execute_sql_trino

        started_at = perf_counter()
        columns, trino_rows = execute_sql_trino(
            query=query,
            max_rows=capped_rows,
            timeout_ms=budget_ms,
            trino_url=trino_url,
            trino_user=trino_user,
            trino_catalog=trino_catalog,
            trino_schema=trino_schema,
        )
        elapsed_ms = (perf_counter() - started_at) * 1000.0
        if elapsed_ms > float(budget_ms):
            raise QueryTimeoutError("query_timeout_exceeded")
        rows = _apply_optional_row_filter(
            columns=columns,
            rows=trino_rows,
            row_filter=row_filter,
            capped_rows=capped_rows,
        )
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))

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
    return QueryResult(columns=columns, rows=rows, row_count=len(rows))


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
