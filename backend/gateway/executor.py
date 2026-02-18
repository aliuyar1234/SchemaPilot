"""SQL execution helpers for gateway."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    """Serialized SQL result set."""

    columns: list[dict[str, str]]
    rows: list[list[object]]
    row_count: int


FILTER_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_filter_column(column: str) -> str:
    normalized = column.strip()
    if not FILTER_COLUMN_RE.match(normalized):
        raise ValueError(f"Invalid ABAC filter column: {column}")
    return normalized


def execute_sql(
    sql: str, *, max_rows: int = 1000, row_filter: tuple[str, str] | None = None
) -> QueryResult:
    """Execute SQL using an in-memory sqlite engine for bootstrap gateway behavior."""
    query = sql or "select 1 as one"
    with sqlite3.connect(":memory:") as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        description = cursor.description or []
        columns = [{"name": item[0], "type": "unknown"} for item in description]
        if row_filter is None:
            rows = cursor.fetchmany(max_rows)
        else:
            filter_column, filter_value = row_filter
            normalized_column = _validate_filter_column(filter_column)
            column_names = [item[0] for item in description]
            try:
                filter_idx = column_names.index(normalized_column)
            except ValueError:
                rows = []
            else:
                all_rows = cursor.fetchall()
                rows = [
                    row for row in all_rows if str(row[filter_idx]) == str(filter_value)
                ][:max_rows]
    serialized_rows = [list(row) for row in rows]
    return QueryResult(columns=columns, rows=serialized_rows, row_count=len(serialized_rows))
