from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_boundary_checker_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/check_boundary_fitness.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "PASS CHK-BOUNDARY-FITNESS" in result.stdout
