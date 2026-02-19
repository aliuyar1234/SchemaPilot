"""Canonical-to-target-db type mapping helpers."""

from __future__ import annotations

CANONICAL_TO_POSTGRES: dict[str, str] = {
    "string": "TEXT",
    "text": "TEXT",
    "integer": "BIGINT",
    "int": "BIGINT",
    "number": "DOUBLE PRECISION",
    "float": "DOUBLE PRECISION",
    "decimal": "NUMERIC",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "datetime": "TIMESTAMP",
    "json": "JSONB",
    "object": "JSONB",
}

CANONICAL_TO_MYSQL: dict[str, str] = {
    "string": "TEXT",
    "text": "TEXT",
    "integer": "BIGINT",
    "int": "BIGINT",
    "number": "DOUBLE",
    "float": "DOUBLE",
    "decimal": "DECIMAL(38,10)",
    "boolean": "TINYINT(1)",
    "bool": "TINYINT(1)",
    "date": "DATE",
    "timestamp": "DATETIME",
    "datetime": "DATETIME",
    "json": "JSON",
    "object": "JSON",
}

CANONICAL_TO_SQLITE: dict[str, str] = {
    "string": "TEXT",
    "text": "TEXT",
    "integer": "INTEGER",
    "int": "INTEGER",
    "number": "REAL",
    "float": "REAL",
    "decimal": "REAL",
    "boolean": "INTEGER",
    "bool": "INTEGER",
    "date": "TEXT",
    "timestamp": "TEXT",
    "datetime": "TEXT",
    "json": "TEXT",
    "object": "TEXT",
}


def map_canonical_type(canonical_type: str | None, *, db_type: str) -> str:
    """Map canonical field type to concrete SQL type for one engine."""
    normalized_db_type = db_type.strip().lower()
    normalized_type = str(canonical_type or "string").strip().lower() or "string"
    if normalized_db_type == "postgres":
        return CANONICAL_TO_POSTGRES.get(normalized_type, "TEXT")
    if normalized_db_type == "mysql":
        return CANONICAL_TO_MYSQL.get(normalized_type, "TEXT")
    if normalized_db_type == "sqlite":
        return CANONICAL_TO_SQLITE.get(normalized_type, "TEXT")
    return "TEXT"

