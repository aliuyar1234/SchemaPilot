"""Read-only database connector for schema discovery and snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class DatabaseTable:
    """Discovered table metadata."""

    schema: str
    name: str


def create_db_engine(database_url: str) -> Engine:
    """Create SQLAlchemy engine for read-only operations."""
    return create_engine(database_url, future=True)


def discover_tables(
    engine: Engine, schema_allowlist: list[str] | None = None
) -> list[DatabaseTable]:
    """Discover table names with optional schema filter."""
    inspector = inspect(engine)
    schemas = schema_allowlist or inspector.get_schema_names()
    tables: list[DatabaseTable] = []
    for schema in schemas:
        for table_name in inspector.get_table_names(schema=schema):
            tables.append(DatabaseTable(schema=schema, name=table_name))
    return sorted(tables, key=lambda item: (item.schema, item.name))


def extract_snapshot(
    engine: Engine, *, table_name: str, schema: str | None = None, row_limit: int = 1000
) -> list[dict[str, object]]:
    """Extract a bounded read-only snapshot from a table."""
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine, schema=schema)
    query = select(table).limit(row_limit)
    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]
