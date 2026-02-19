"""Deterministic DDL generation from semantic manifest state."""

from __future__ import annotations

import re
from collections.abc import Mapping

from backend.shared_domain.semantic import validate_semantic_manifest
from backend.shared_domain.target_db.type_mapping import map_canonical_type

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def generate_target_db_ddl(
    *,
    manifest: Mapping[str, object],
    db_type: str,
    schema: str | None = None,
) -> list[str]:
    """Generate deterministic CREATE TABLE statements for semantic entities."""
    normalized_manifest = validate_semantic_manifest(manifest)
    normalized_db_type = db_type.strip().lower()
    schema_prefix = _schema_prefix(schema=schema, db_type=normalized_db_type)
    statements: list[str] = []
    entities_raw = normalized_manifest.get("entities", [])
    if not isinstance(entities_raw, list):
        return statements

    for entity in entities_raw:
        if not isinstance(entity, dict):
            continue
        entity_id = _safe_identifier(str(entity.get("entity_id", "")))
        primary_key = _safe_identifier(str(entity.get("primary_key", "")))
        attributes_raw = entity.get("attributes", [])
        attributes = (
            sorted({str(item).strip() for item in attributes_raw if str(item).strip()})
            if isinstance(attributes_raw, list)
            else []
        )
        attribute_types_raw = entity.get("attribute_types", {})
        attribute_types = attribute_types_raw if isinstance(attribute_types_raw, dict) else {}

        column_specs: list[str] = []
        pk_type = map_canonical_type(
            _as_type_name(attribute_types.get(primary_key)),
            db_type=normalized_db_type,
        )
        column_specs.append(
            f"{_quoted_identifier(primary_key, db_type=normalized_db_type)} {pk_type} NOT NULL"
        )
        for attribute in attributes:
            normalized_attribute = _safe_identifier(attribute)
            if normalized_attribute == primary_key:
                continue
            sql_type = map_canonical_type(
                _as_type_name(attribute_types.get(normalized_attribute)),
                db_type=normalized_db_type,
            )
            column_specs.append(
                f"{_quoted_identifier(normalized_attribute, db_type=normalized_db_type)} "
                f"{sql_type} NULL"
            )
        pk_clause = (
            f"PRIMARY KEY ({_quoted_identifier(primary_key, db_type=normalized_db_type)})"
        )
        rendered_columns = ", ".join([*column_specs, pk_clause])
        table_name = f"{schema_prefix}{_quoted_identifier(entity_id, db_type=normalized_db_type)}"
        statements.append(f"CREATE TABLE IF NOT EXISTS {table_name} ({rendered_columns})")
    return statements


def migration_drop_statements(
    *,
    previous_manifest: Mapping[str, object] | None,
    current_manifest: Mapping[str, object],
    db_type: str,
    schema: str | None = None,
) -> list[str]:
    """Generate deterministic DROP TABLE statements for removed entities."""
    if previous_manifest is None:
        return []
    normalized_previous = validate_semantic_manifest(previous_manifest)
    normalized_current = validate_semantic_manifest(current_manifest)
    previous_entities = _entity_ids(normalized_previous)
    current_entities = _entity_ids(normalized_current)
    removed = sorted(previous_entities.difference(current_entities))
    normalized_db_type = db_type.strip().lower()
    schema_prefix = _schema_prefix(schema=schema, db_type=normalized_db_type)
    return [
        (
            "DROP TABLE IF EXISTS "
            f"{schema_prefix}{_quoted_identifier(entity_id, db_type=normalized_db_type)}"
        )
        for entity_id in removed
    ]


def _entity_ids(manifest: Mapping[str, object]) -> set[str]:
    entities = manifest.get("entities", [])
    if not isinstance(entities, list):
        return set()
    result: set[str] = set()
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        result.add(_safe_identifier(str(entity.get("entity_id", ""))))
    return result


def _schema_prefix(*, schema: str | None, db_type: str) -> str:
    if db_type == "sqlite":
        return ""
    normalized = str(schema or "").strip()
    if not normalized:
        return ""
    safe_schema = _safe_identifier(normalized)
    return f"{_quoted_identifier(safe_schema, db_type=db_type)}."


def _quoted_identifier(name: str, *, db_type: str) -> str:
    if db_type == "mysql":
        return f"`{name}`"
    return f'"{name}"'


def _safe_identifier(value: str) -> str:
    normalized = value.strip()
    if not IDENTIFIER_RE.match(normalized):
        raise ValueError(f"invalid_identifier:{value}")
    return normalized


def _as_type_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized or None
    return str(value).strip().lower() or None

