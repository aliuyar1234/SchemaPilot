from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_security_fuzz_tool_runs_and_writes_report(tmp_path: Path) -> None:
    output_path = tmp_path / "fuzz_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/security_fuzz.py",
            "--iterations",
            "10",
            "--seed",
            "42",
            "--output",
            output_path.as_posix(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert int(report["checked"]) >= 10
