from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.check_boundary_fitness import CheckState, check_python


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


def test_boundary_checker_flags_unregistered_backend_root(tmp_path: Path) -> None:
    rules_path = Path(__file__).resolve().parents[1] / "tools" / "boundary_rules.json"
    rules = json.loads(rules_path.read_text())
    repo = tmp_path
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "backend" / "control_plane").mkdir(parents=True, exist_ok=True)
    (repo / "backend" / "rogue").mkdir(parents=True, exist_ok=True)
    (repo / "backend" / "control_plane" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "backend" / "rogue" / "module.py").write_text(
        "from backend.gateway import app\n",
        encoding="utf-8",
    )
    state = CheckState()
    check_python(repo, rules, state)
    assert any("Unregistered module root" in violation for violation in state.violations)
