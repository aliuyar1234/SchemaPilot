#!/usr/bin/env python3
"""Backup/restore drill for local metadata and storage pointers."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path


def _write_seed_state(db_path: Path, storage_path: Path) -> None:
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "gold_latest.json").write_text(
        json.dumps({"snapshot_id": "snap_001"}, sort_keys=True),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, status TEXT)")
        cursor.execute(
            "INSERT OR REPLACE INTO runs (run_id, status) VALUES (?, ?)",
            ("run_001", "succeeded"),
        )
        connection.commit()


def _verify_restored_state(db_path: Path, storage_path: Path) -> tuple[int, str]:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?", ("run_001",))
        run_count = int(cursor.fetchone()[0])
    latest = json.loads((storage_path / "gold_latest.json").read_text(encoding="utf-8"))
    return run_count, str(latest.get("snapshot_id", ""))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    drill_root = root / "runtime" / "backup_restore_drill"
    source_dir = drill_root / "source"
    backup_dir = drill_root / "backup"
    restored_dir = drill_root / "restored"

    if drill_root.exists():
        shutil.rmtree(drill_root)
    source_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    restored_dir.mkdir(parents=True, exist_ok=True)

    source_db = source_dir / "metadata.db"
    source_storage = source_dir / "storage"
    _write_seed_state(source_db, source_storage)

    shutil.copy2(source_db, backup_dir / "metadata.db")
    shutil.copytree(source_storage, backup_dir / "storage", dirs_exist_ok=True)

    shutil.copy2(backup_dir / "metadata.db", restored_dir / "metadata.db")
    shutil.copytree(backup_dir / "storage", restored_dir / "storage", dirs_exist_ok=True)

    run_count, snapshot_id = _verify_restored_state(
        restored_dir / "metadata.db",
        restored_dir / "storage",
    )
    if run_count != 1 or snapshot_id != "snap_001":
        print("FAIL CHK-BACKUP-RESTORE")
        return 1

    report_path = drill_root / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "run_count": run_count,
                "snapshot_id": snapshot_id,
                "restored_db": (restored_dir / "metadata.db").relative_to(root).as_posix(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print("PASS CHK-BACKUP-RESTORE")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
