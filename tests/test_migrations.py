from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_alembic_migration_upgrade_and_downgrade() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/migration_check.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PASS CHK-MIGRATIONS" in result.stdout
