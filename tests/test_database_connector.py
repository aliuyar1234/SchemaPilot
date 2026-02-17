from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from backend.workers.connectors.database import create_db_engine, discover_tables, extract_snapshot


def test_database_connector_discovery_and_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "source.db"
    engine = create_db_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("create table invoices (id integer, amount integer)"))
        connection.execute(text("insert into invoices values (1, 100), (2, 200)"))

    tables = discover_tables(engine, schema_allowlist=["main"])
    assert any(table.name == "invoices" for table in tables)

    rows = extract_snapshot(engine, table_name="invoices", schema="main", row_limit=10)
    assert len(rows) == 2
    assert rows[0]["amount"] == 100
