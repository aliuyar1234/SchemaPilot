"""Safe query template library with deterministic rendering."""

from __future__ import annotations

import json
import re
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
SAFE_PARAM_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def load_query_templates(*, path: Path | None = None) -> list[dict[str, object]]:
    """Load query templates from canonical pack file."""
    resolved = path or Path(__file__).resolve().parents[2] / "packs" / "query_templates.json"
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []
    templates_raw = raw.get("templates", [])
    if not isinstance(templates_raw, list):
        return []
    templates: list[dict[str, object]] = []
    for row in templates_raw:
        if not isinstance(row, dict):
            continue
        template_id = str(row.get("template_id", "")).strip()
        sql = str(row.get("sql", "")).strip()
        if not template_id or not sql:
            continue
        required_params = sorted({str(item).strip() for item in _extract_placeholders(sql)})
        templates.append(
            {
                "template_id": template_id,
                "name": str(row.get("name", template_id)).strip() or template_id,
                "description": str(row.get("description", "")).strip(),
                "dataset_id": str(row.get("dataset_id", "")).strip(),
                "sql": sql,
                "required_params": required_params,
            }
        )
    return sorted(templates, key=lambda item: str(item["template_id"]))


def list_query_template_summaries(*, path: Path | None = None) -> list[dict[str, object]]:
    """Return compact deterministic template summaries."""
    summaries: list[dict[str, object]] = []
    for row in load_query_templates(path=path):
        summaries.append(
            {
                "template_id": row["template_id"],
                "name": row["name"],
                "description": row["description"],
                "dataset_id": row["dataset_id"],
                "required_params": row["required_params"],
            }
        )
    return summaries


def render_query_template(
    *,
    template_id: str,
    params: dict[str, object] | None = None,
    path: Path | None = None,
) -> dict[str, object]:
    """Render a query template with strict parameter validation."""
    normalized_id = template_id.strip()
    selected = None
    for row in load_query_templates(path=path):
        if str(row.get("template_id", "")) == normalized_id:
            selected = row
            break
    if selected is None:
        raise ValueError("query_template_not_found")
    sql = str(selected.get("sql", ""))
    placeholders = _extract_placeholders(sql)
    params_payload = params or {}
    rendered_sql = sql
    missing: list[str] = []
    for placeholder in placeholders:
        raw_value = params_payload.get(placeholder)
        if raw_value is None:
            missing.append(placeholder)
            continue
        value = str(raw_value).strip()
        if not value or not SAFE_PARAM_RE.match(value):
            raise ValueError(f"invalid_template_param:{placeholder}")
        rendered_sql = re.sub(
            r"\{\{\s*" + re.escape(placeholder) + r"\s*\}\}",
            value,
            rendered_sql,
        )
    if missing:
        raise ValueError("missing_template_params:" + ",".join(sorted(missing)))
    if PLACEHOLDER_RE.search(rendered_sql):
        raise ValueError("unresolved_template_params")
    return {
        "template_id": selected["template_id"],
        "name": selected["name"],
        "dataset_id": selected["dataset_id"],
        "required_params": sorted(placeholders),
        "sql": rendered_sql,
    }


def _extract_placeholders(sql: str) -> list[str]:
    return sorted({match.group(1) for match in PLACEHOLDER_RE.finditer(sql)})
