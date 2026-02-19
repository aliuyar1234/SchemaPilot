from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_connector_conformance_tool_passes_with_fixture_exports(tmp_path: Path) -> None:
    output_path = tmp_path / "conformance_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/connector_conformance.py",
            "--root",
            (tmp_path / "exports").as_posix(),
            "--output",
            output_path.as_posix(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output_path.exists()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["strict_tier"] == "recommended"
    assert len(report["results"]) >= 5
    tiers = {str(item.get("tier", "")) for item in report["results"]}
    assert "recommended" in tiers
    assert any(
        item.get("tier") == "community" and item.get("required_for_gate") is False
        for item in report["results"]
    )
