"""Trino query adapter for gateway execution path."""

from __future__ import annotations

import json
from urllib import request as urlrequest


def execute_sql_trino(
    *,
    query: str,
    max_rows: int,
    timeout_ms: int,
    trino_url: str,
    trino_user: str,
    trino_catalog: str,
    trino_schema: str,
) -> tuple[list[dict[str, str]], list[list[object]]]:
    """Execute read-only SQL through Trino HTTP protocol."""
    statement_url = trino_url.rstrip("/") + "/v1/statement"
    timeout_seconds = max(1.0, float(timeout_ms) / 1000.0)
    payload = query.encode("utf-8")
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Trino-User": trino_user,
        "X-Trino-Catalog": trino_catalog,
        "X-Trino-Schema": trino_schema,
    }
    response = _request_json(
        method="POST",
        url=statement_url,
        payload=payload,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    columns = _extract_columns(response)
    rows = _extract_rows(response, max_rows=max_rows)
    next_uri = str(response.get("nextUri", "")).strip()
    page_budget = 50
    while next_uri and len(rows) < max_rows and page_budget > 0:
        page_budget -= 1
        page = _request_json(
            method="GET",
            url=next_uri,
            payload=None,
            headers={},
            timeout_seconds=timeout_seconds,
        )
        if not columns:
            columns = _extract_columns(page)
        rows.extend(_extract_rows(page, max_rows=max_rows - len(rows)))
        next_uri = str(page.get("nextUri", "")).strip()
    return columns, rows[:max_rows]


def _request_json(
    *,
    method: str,
    url: str,
    payload: bytes | None,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, object]:
    request = urlrequest.Request(
        url=url,
        data=payload,
        method=method,
        headers=headers,
    )
    with urlrequest.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Trino response must be a JSON object.")
    return parsed


def _extract_columns(response: dict[str, object]) -> list[dict[str, str]]:
    columns_raw = response.get("columns", [])
    if not isinstance(columns_raw, list):
        return []
    columns: list[dict[str, str]] = []
    for row in columns_raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        columns.append({"name": name, "type": str(row.get("type", "unknown"))})
    return columns


def _extract_rows(response: dict[str, object], *, max_rows: int) -> list[list[object]]:
    data_raw = response.get("data", [])
    if not isinstance(data_raw, list):
        return []
    rows: list[list[object]] = []
    for row in data_raw:
        if not isinstance(row, list):
            continue
        rows.append(list(row))
        if len(rows) >= max_rows:
            break
    return rows
