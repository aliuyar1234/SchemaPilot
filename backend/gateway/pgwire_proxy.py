"""Minimal PGWire-compatible query payload shim (HTTP transport)."""

from __future__ import annotations

import re

SELECT_LIKE_PATTERN = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def normalize_pgwire_payload(payload: dict[str, object]) -> dict[str, object]:
    """Translate PGWire proxy payload into gateway query payload."""
    workspace_id = str(payload.get("workspace_id", "")).strip()
    sql = str(payload.get("sql", "")).strip()
    if not workspace_id:
        raise ValueError("workspace_id_required")
    if not sql:
        raise ValueError("sql_required")
    if not SELECT_LIKE_PATTERN.match(sql):
        raise ValueError("pgwire_select_only")
    dataset_id_raw = payload.get("dataset_id")
    max_rows_raw = payload.get("max_rows", 100)
    max_rows = int(max_rows_raw) if isinstance(max_rows_raw, (int, float, str)) else 100
    normalized: dict[str, object] = {
        "workspace_id": workspace_id,
        "query": {"language": "sql", "text": sql},
        "max_rows": max(max_rows, 1),
        "pgwire_proxy": True,
    }
    if dataset_id_raw is not None and str(dataset_id_raw).strip():
        normalized["resource_attributes"] = {"dataset_id": str(dataset_id_raw).strip()}
    return normalized

