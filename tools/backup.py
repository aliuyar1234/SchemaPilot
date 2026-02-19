#!/usr/bin/env python3
"""Create a deterministic backup snapshot for metadata DB and storage artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def backup_runtime_state(*, source_db: Path, source_storage: Path, output_dir: Path) -> Path:
    if not source_db.exists() or not source_db.is_file():
        raise ValueError(f"backup_metadata_db_missing:{source_db.as_posix()}")
    if not source_storage.exists() or not source_storage.is_dir():
        raise ValueError(f"backup_storage_missing:{source_storage.as_posix()}")
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_db = output_dir / "metadata.db"
    backup_storage = output_dir / "storage"
    shutil.copy2(source_db, backup_db)
    shutil.copytree(source_storage, backup_storage, dirs_exist_ok=True)
    manifest = {
        "metadata_db": backup_db.name,
        "storage_dir": backup_storage.name,
        "status": "pass",
    }
    manifest_path = output_dir / "backup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup runtime metadata and storage state.")
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--source-storage", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source_db = Path(args.source_db)
    source_storage = Path(args.source_storage)
    output_dir = Path(args.output_dir)
    manifest_path = backup_runtime_state(
        source_db=source_db, source_storage=source_storage, output_dir=output_dir
    )
    print(manifest_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
