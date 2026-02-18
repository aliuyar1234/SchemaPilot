from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_secrets_rotation_drill_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/secrets_rotation_drill.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PASS secrets rotation drill" in result.stdout
    report = json.loads(
        (root / "runtime" / "secrets_rotation_drill" / "report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "pass"
