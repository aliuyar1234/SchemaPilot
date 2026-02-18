from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_semantic_validate_tool_passes_for_example_manifest(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output_file = tmp_path / "manifest.json"
    output_file.write_text(
        (root / "backend" / "shared_domain" / "semantic_manifest.example.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "tools/semantic_validate.py", output_file.as_posix()],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "PASS semantic manifest validation" in result.stdout
    checksum_line = result.stdout.strip().splitlines()[-1]
    parsed = json.loads(checksum_line)
    assert "checksum" in parsed


def test_semantic_validate_tool_fails_for_invalid_manifest(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    invalid = {
        "manifest_version": "1",
        "workspace_id": "w1",
        "entities": [],
        "metrics": [
            {
                "metric_id": "broken",
                "entity_id": "missing_entity",
                "aggregation": "sum",
                "field": "value",
                "expression": "sum(value)",
            }
        ],
        "joins": [],
    }
    path = tmp_path / "invalid_semantic.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "tools/semantic_validate.py", path.as_posix()],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL semantic manifest validation" in result.stdout
