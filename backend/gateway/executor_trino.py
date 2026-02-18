"""Trino query adapter for gateway execution path."""

from __future__ import annotations

import json
from time import perf_counter, sleep
from urllib import error as urlerror
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
    max_retries: int = 2,
) -> tuple[list[dict[str, str]], list[list[object]]]:
    """Execute read-only SQL through Trino HTTP protocol."""
    statement_url = trino_url.rstrip("/") + "/v1/statement"
    timeout_seconds = max(1.0, float(timeout_ms) / 1000.0)
    deadline = perf_counter() + timeout_seconds
    payload = query.encode("utf-8")
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Trino-User": trino_user,
        "X-Trino-Catalog": trino_catalog,
        "X-Trino-Schema": trino_schema,
    }
    try:
        response = _request_json_with_retries(
            method="POST",
            url=statement_url,
            payload=payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    except ValueError as exc:
        if "timeout" in str(exc).lower():
            raise TimeoutError("trino_query_timeout") from exc
        raise
    query_id = str(response.get("id", "")).strip()
    columns = _extract_columns(response)
    rows = _extract_rows(response, max_rows=max_rows)
    next_uri = str(response.get("nextUri", "")).strip()
    page_budget = 50
    while next_uri and len(rows) < max_rows and page_budget > 0:
        if perf_counter() > deadline:
            cancel_trino_query(
                trino_url=trino_url,
                query_id=query_id,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
            raise TimeoutError("trino_query_timeout")
        page_budget -= 1
        try:
            page = _request_json_with_retries(
                method="GET",
                url=next_uri,
                payload=None,
                headers={},
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        except ValueError as exc:
            if "timeout" in str(exc).lower():
                cancel_trino_query(
                    trino_url=trino_url,
                    query_id=query_id,
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                )
                raise TimeoutError("trino_query_timeout") from exc
            raise
        if not query_id:
            query_id = str(page.get("id", "")).strip()
        if not columns:
            columns = _extract_columns(page)
        rows.extend(_extract_rows(page, max_rows=max_rows - len(rows)))
        next_uri = str(page.get("nextUri", "")).strip()
    return columns, rows[:max_rows]


def cancel_trino_query(
    *,
    trino_url: str,
    query_id: str,
    timeout_seconds: float,
    max_retries: int,
) -> None:
    """Attempt to cancel a running Trino query by id."""
    normalized_query_id = query_id.strip()
    if not normalized_query_id:
        return
    cancel_url = trino_url.rstrip("/") + "/v1/query/" + normalized_query_id
    try:
        _request_json_with_retries(
            method="DELETE",
            url=cancel_url,
            payload=None,
            headers={},
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    except Exception:
        # Cancellation is best-effort; caller enforces fail-closed timeout.
        return


def _request_json_with_retries(
    *,
    method: str,
    url: str,
    payload: bytes | None,
    headers: dict[str, str],
    timeout_seconds: float,
    max_retries: int,
) -> dict[str, object]:
    attempts = max(1, max_retries + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _request_json(
                method=method,
                url=url,
                payload=payload,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except (OSError, TimeoutError, urlerror.URLError, ValueError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            sleep(min(0.25 * attempt, 0.5))
    if last_error is None:
        raise ValueError("trino_request_failed")
    raise ValueError(f"trino_request_failed:{last_error}") from last_error


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
        body = response.read().decode("utf-8", errors="ignore")
    if not body.strip():
        return {}
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
