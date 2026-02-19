from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_report(path: Path, *, scenario_id: str, result: str, reason: str) -> None:
    payload = {
        "workspace_id": "w1",
        "scenario_count": 1,
        "scenarios": [
            {
                "id": scenario_id,
                "result": result,
                "reason": reason,
                "applied_masks": {},
                "applied_filters": {},
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_policy_diff_tool_generates_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "policy_diff.json"
    _write_report(before, scenario_id="s1", result="allow", reason="allow")
    _write_report(after, scenario_id="s1", result="allow", reason="allow")
    result = subprocess.run(
        [
            sys.executable,
            "tools/policy_diff.py",
            "--before",
            before.as_posix(),
            "--after",
            after.as_posix(),
            "--output",
            output.as_posix(),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.exists()
    parsed = json.loads(output.read_text(encoding="utf-8"))
    assert parsed["status"] == "unchanged"


def test_policy_diff_tool_fails_when_protected_scenario_denied(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "policy_diff.json"
    _write_report(before, scenario_id="s1", result="allow", reason="allow")
    _write_report(after, scenario_id="s1", result="deny", reason="policy_denied")
    result = subprocess.run(
        [
            sys.executable,
            "tools/policy_diff.py",
            "--before",
            before.as_posix(),
            "--after",
            after.as_posix(),
            "--output",
            output.as_posix(),
            "--protected-scenario-id",
            "s1",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "protected scenarios regressed to deny" in result.stdout
