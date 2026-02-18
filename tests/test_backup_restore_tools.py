from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tools.backup import backup_runtime_state
from tools.restore import restore_runtime_state


def _seed_source_state(db_path: Path, storage_dir: Path) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "gold_latest.json").write_text(
        json.dumps({"snapshot_id": "snap_test"}, sort_keys=True), encoding="utf-8"
    )
    with sqlite3.connect(db_path.as_posix()) as connection:
        connection.execute("create table if not exists runs (run_id text primary key, status text)")
        connection.execute(
            "insert or replace into runs (run_id, status) values (?, ?)",
            ("run_test", "succeeded"),
        )
        connection.commit()


def test_backup_and_restore_tools_roundtrip(tmp_path: Path) -> None:
    source_db = tmp_path / "source" / "metadata.db"
    source_storage = tmp_path / "source" / "storage"
    source_db.parent.mkdir(parents=True, exist_ok=True)
    _seed_source_state(source_db, source_storage)

    backup_dir = tmp_path / "backup"
    restore_dir = tmp_path / "restored"
    backup_manifest = backup_runtime_state(
        source_db=source_db,
        source_storage=source_storage,
        output_dir=backup_dir,
    )
    restore_manifest = restore_runtime_state(
        backup_dir=backup_dir,
        restore_dir=restore_dir,
    )

    assert backup_manifest.exists()
    assert restore_manifest.exists()

    restored_latest = json.loads((restore_dir / "storage" / "gold_latest.json").read_text())
    assert restored_latest["snapshot_id"] == "snap_test"

    with sqlite3.connect((restore_dir / "metadata.db").as_posix()) as connection:
        row = connection.execute(
            "select status from runs where run_id = ?",
            ("run_test",),
        ).fetchone()
    assert row is not None
    assert row[0] == "succeeded"
