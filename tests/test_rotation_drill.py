from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_rotation_drill_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/rotation_drill.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS rotation drill" in result.stdout
    report = json.loads((root / "runtime" / "rotation_drill" / "report.json").read_text("utf-8"))
    assert report["status"] == "pass"
    assert report["gateway_reader_rotated"] is True
    assert report["worker_writer_rotated"] is True
    assert report["jwks_cache_invalidated"] is True
