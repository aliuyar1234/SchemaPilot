from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_breakglass_drill_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/breakglass_drill.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS breakglass drill" in result.stdout
    report = json.loads(
        (root / "runtime" / "breakglass_drill" / "report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "pass"
    assert report["breakglass_tagged_query"] is True
    assert report["auto_revoked"] is True
    assert report["request_status"] == "expired"
    assert report["grant_status"] == "expired"
