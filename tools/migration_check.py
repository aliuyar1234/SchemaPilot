#!/usr/bin/env python3
"""Apply and roll back Alembic migrations to validate safety."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def build_temp_alembic_ini(root: Path, database_url: str) -> Path:
    source = (root / "alembic.ini").read_text(encoding="utf-8")
    updated = []
    for line in source.splitlines():
        if line.startswith("sqlalchemy.url = "):
            updated.append(f"sqlalchemy.url = {database_url}")
        else:
            updated.append(line)
    fd, path = tempfile.mkstemp(prefix="alembic_", suffix=".ini")
    os.close(fd)
    Path(path).write_text("\n".join(updated) + "\n", encoding="utf-8")
    return Path(path)


def run(cmd: list[str], cwd: Path) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    temp_db = tempfile.NamedTemporaryFile(prefix="schemapilot_migrate_", suffix=".db", delete=False)
    temp_db.close()
    db_url = f"sqlite:///{temp_db.name.replace('\\', '/')}"
    ini_path = build_temp_alembic_ini(root, db_url)
    try:
        run([sys.executable, "-m", "alembic", "-c", str(ini_path), "upgrade", "head"], cwd=root)
        run([sys.executable, "-m", "alembic", "-c", str(ini_path), "downgrade", "base"], cwd=root)
    finally:
        ini_path.unlink(missing_ok=True)
        Path(temp_db.name).unlink(missing_ok=True)
    print("PASS CHK-MIGRATIONS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
