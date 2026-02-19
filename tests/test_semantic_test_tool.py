from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_semantic_test_tool_passes_for_repo_registry(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "semantic_test_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/semantic_test.py",
            "--registry",
            "packs/registry.json",
            "--output",
            output.as_posix(),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["pack_count"] >= 1


def test_semantic_test_tool_fails_for_invalid_metric_entity(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    packs_root = tmp_path / "packs"
    semantic_dir = packs_root / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    invalid_pack_path = semantic_dir / "broken.json"
    invalid_pack_path.write_text(
        json.dumps(
            {
                "pack_id": "broken",
                "schema_version": "v2",
                "version": "1.0.0",
                "semantic_manifest": {
                    "manifest_version": "1",
                    "entities": [{"entity_id": "invoice", "dataset_id": "dataset-invoices"}],
                    "metrics": [
                        {
                            "metric_id": "broken_metric",
                            "entity_id": "missing_entity",
                            "expression": "count(*)",
                        }
                    ],
                    "joins": [],
                },
            }
        ),
        encoding="utf-8",
    )
    registry_path = packs_root / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "registry_version": "v1",
                "policy_packs": [],
                "semantic_packs": [{"pack_id": "broken", "path": invalid_pack_path.as_posix()}],
                "template_packs": [],
                "connector_examples": [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "semantic_test_report.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/semantic_test.py",
            "--registry",
            registry_path.as_posix(),
            "--output",
            output.as_posix(),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "fail"
    errors = report["results"][0]["errors"]
    assert "metric_entity_not_found:broken_metric" in errors
