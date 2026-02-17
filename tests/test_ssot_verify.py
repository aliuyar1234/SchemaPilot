from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_ssot_verify_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/ssot_verify.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "CHK-REF-INTEGRITY: PASS" in result.stdout
