#!/usr/bin/env python3
"""Restore metadata DB and storage artifacts from a backup snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def restore_runtime_state(*, backup_dir: Path, restore_dir: Path) -> Path:
    restore_dir.mkdir(parents=True, exist_ok=True)
    backup_db = backup_dir / "metadata.db"
    backup_storage = backup_dir / "storage"
    restored_db = restore_dir / "metadata.db"
    restored_storage = restore_dir / "storage"
    shutil.copy2(backup_db, restored_db)
    shutil.copytree(backup_storage, restored_storage, dirs_exist_ok=True)
    manifest = {
        "metadata_db": restored_db.name,
        "storage_dir": restored_storage.name,
        "status": "pass",
    }
    manifest_path = restore_dir / "restore_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore runtime metadata and storage state.")
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--restore-dir", required=True)
    args = parser.parse_args()

    manifest_path = restore_runtime_state(
        backup_dir=Path(args.backup_dir),
        restore_dir=Path(args.restore_dir),
    )
    print(manifest_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
