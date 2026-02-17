"""SQL execution helpers for gateway."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    """Serialized SQL result set."""

    columns: list[dict[str, str]]
    rows: list[list[object]]
    row_count: int


def execute_sql(sql: str, *, max_rows: int = 1000) -> QueryResult:
    """Execute SQL using an in-memory sqlite engine for bootstrap gateway behavior."""
    with sqlite3.connect(":memory:") as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(max_rows)
        description = cursor.description or []
        columns = [{"name": item[0], "type": "unknown"} for item in description]
    serialized_rows = [list(row) for row in rows]
    return QueryResult(columns=columns, rows=serialized_rows, row_count=len(serialized_rows))
