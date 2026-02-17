from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_messybench_harness_produces_machine_readable_results() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/messybench_harness.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PASS MessyBench harness" in result.stdout
    report_path = root / "runtime" / "messybench" / "results.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert len(report["checks"]) >= 3
