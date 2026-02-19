from __future__ import annotations

from pathlib import Path

from backend.workers.connectors.db_dumps import discover


def test_db_dump_connector_discovers_sql_and_dump_files(tmp_path: Path) -> None:
    (tmp_path / "postgres_full.sql").write_text("create table invoices(id int);", encoding="utf-8")
    (tmp_path / "mysql_full.dump").write_text("mysqldump payload", encoding="utf-8")
    rows = discover({"root_path": tmp_path.as_posix()})
    assert len(rows) == 2
    families = {str(row["dataset_family"]) for row in rows}
    assert "postgres_dump" in families or "db_dump" in families


def test_db_dump_connector_requires_existing_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    try:
        discover({"root_path": missing.as_posix()})
    except ValueError as exc:
        assert str(exc) == "root_path_not_found"
    else:  # pragma: no cover
        raise AssertionError("expected root_path_not_found")

