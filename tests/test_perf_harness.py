from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_perf_harness_passes_against_baseline() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/perf_harness.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PASS CHK-PERF-HARNESS" in result.stdout
    report = json.loads((root / "runtime" / "perf" / "results.json").read_text(encoding="utf-8"))
    assert report["status"] == "pass"
