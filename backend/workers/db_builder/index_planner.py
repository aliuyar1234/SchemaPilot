"""Deterministic index/constraint planning for target DB builds."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class IndexPlan:
    """Index/constraint recommendation bundle."""

    plan_checksum: str
    statements: list[str]
    indexes: list[dict[str, object]]
    constraints: list[dict[str, object]]


def build_index_constraint_plan(
    *,
    workspace_id: str,
    target_db_id: str,
    db_type: str,
    schema: str | None,
    target_build_id: str,
    semantic_manifest: dict[str, object],
    include_constraints: bool,
) -> IndexPlan:
    """Build conservative index/constraint statements from semantic entities."""
    entities_raw = semantic_manifest.get("entities", [])
    entities = entities_raw if isinstance(entities_raw, list) else []
    index_rows: list[dict[str, object]] = []
    constraint_rows: list[dict[str, object]] = []
    for entity_raw in entities:
        if not isinstance(entity_raw, dict):
            continue
        table = _safe_identifier(entity_raw.get("entity_id"))
        if table is None:
            continue
        primary_key = _safe_identifier(entity_raw.get("primary_key"))
        attrs_raw = entity_raw.get("attributes", [])
        attrs = attrs_raw if isinstance(attrs_raw, list) else []

        if primary_key is not None:
            index_rows.append(
                {
                    "table": table,
                    "columns": [primary_key],
                    "kind": "primary_key_lookup",
                }
            )
            if include_constraints:
                constraint_rows.append(
                    {
                        "table": table,
                        "constraint_name": f"pk_{table}",
                        "type": "primary_key",
                        "columns": [primary_key],
                    }
                )
        for attr in attrs:
            column = _safe_identifier(attr)
            if column is None:
                continue
            if column == primary_key:
                continue
            if not column.endswith("_id"):
                continue
            index_rows.append(
                {
                    "table": table,
                    "columns": [column],
                    "kind": "join_key_lookup",
                }
            )

    deduped_indexes = _dedupe_index_rows(index_rows)
    deduped_constraints = _dedupe_constraint_rows(constraint_rows)
    statements = _render_statements(
        db_type=db_type,
        schema=schema,
        indexes=deduped_indexes,
        constraints=deduped_constraints,
    )
    checksum = _stable_checksum(
        {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "target_build_id": target_build_id,
            "db_type": db_type,
            "schema": schema or "",
            "indexes": deduped_indexes,
            "constraints": deduped_constraints,
            "statements": statements,
        }
    )
    return IndexPlan(
        plan_checksum=checksum,
        statements=statements,
        indexes=deduped_indexes,
        constraints=deduped_constraints,
    )


def _safe_identifier(value: object) -> str | None:
    candidate = str(value).strip()
    if not candidate:
        return None
    if not _SAFE_IDENTIFIER.fullmatch(candidate):
        return None
    return candidate.lower()


def _stable_checksum(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _dedupe_index_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    deduped: list[dict[str, object]] = []
    for row in sorted(
        rows,
        key=lambda item: (
            str(item.get("table", "")),
            _columns_tuple(item.get("columns", [])),
        ),
    ):
        table = str(row.get("table", "")).strip()
        columns_raw = row.get("columns", [])
        columns = (
            tuple(str(value).strip() for value in columns_raw if str(value).strip())
            if isinstance(columns_raw, list)
            else ()
        )
        if not table or not columns:
            continue
        key = (table, columns)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "table": table,
                "columns": list(columns),
                "kind": str(row.get("kind", "lookup")),
            }
        )
    return deduped


def _columns_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _dedupe_constraint_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, object]] = []
    for row in sorted(
        rows,
        key=lambda item: (
            str(item.get("table", "")),
            str(item.get("constraint_name", "")),
        ),
    ):
        table = str(row.get("table", "")).strip()
        constraint_name = str(row.get("constraint_name", "")).strip()
        columns_raw = row.get("columns", [])
        columns = (
            [str(value).strip() for value in columns_raw if str(value).strip()]
            if isinstance(columns_raw, list)
            else []
        )
        if not table or not constraint_name or not columns:
            continue
        key = (table, constraint_name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "table": table,
                "constraint_name": constraint_name,
                "type": str(row.get("type", "constraint")),
                "columns": columns,
            }
        )
    return deduped


def _render_statements(
    *,
    db_type: str,
    schema: str | None,
    indexes: list[dict[str, object]],
    constraints: list[dict[str, object]],
) -> list[str]:
    normalized_db = db_type.strip().lower()
    statements: list[str] = []
    for row in indexes:
        table = str(row.get("table", "")).strip()
        columns_raw = row.get("columns", [])
        columns = (
            [str(item) for item in columns_raw if str(item).strip()]
            if isinstance(columns_raw, list)
            else []
        )
        if not table or not columns:
            continue
        index_name = f"idx_{table}_{'_'.join(columns)}"
        qualified_table = _qualified_table(
            db_type=normalized_db,
            schema=schema,
            table=table,
        )
        column_sql = ", ".join(_quote_identifier(normalized_db, item) for item in columns)
        statements.append(
            f"CREATE INDEX IF NOT EXISTS {_quote_identifier(normalized_db, index_name)} "
            f"ON {qualified_table} ({column_sql});"
        )
    if normalized_db == "sqlite":
        return statements
    for row in constraints:
        table = str(row.get("table", "")).strip()
        constraint_name = str(row.get("constraint_name", "")).strip()
        columns_raw = row.get("columns", [])
        columns = (
            [str(item) for item in columns_raw if str(item).strip()]
            if isinstance(columns_raw, list)
            else []
        )
        if not table or not constraint_name or not columns:
            continue
        qualified_table = _qualified_table(
            db_type=normalized_db,
            schema=schema,
            table=table,
        )
        column_sql = ", ".join(_quote_identifier(normalized_db, item) for item in columns)
        statements.append(
            f"ALTER TABLE {qualified_table} ADD CONSTRAINT "
            f"{_quote_identifier(normalized_db, constraint_name)} PRIMARY KEY ({column_sql});"
        )
    return statements


def _qualified_table(*, db_type: str, schema: str | None, table: str) -> str:
    quoted_table = _quote_identifier(db_type, table)
    if not schema:
        return quoted_table
    return f"{_quote_identifier(db_type, schema)}.{quoted_table}"


def _quote_identifier(db_type: str, identifier: str) -> str:
    if db_type == "mysql":
        return f"`{identifier}`"
    return f'"{identifier}"'
