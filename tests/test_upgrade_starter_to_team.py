from __future__ import annotations

import json
from pathlib import Path

from tools.upgrade_starter_to_team import run_upgrade


def test_upgrade_starter_to_team_preserves_dataset_ids(tmp_path: Path) -> None:
    manifest = (
        tmp_path
        / "bronze"
        / "w1"
        / "source-1"
        / "dataset-1"
        / "2026-02-17"
        / "artifact_a"
        / "manifest.json"
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"content_hash": "x"}), encoding="utf-8")

    report = run_upgrade(storage_root=tmp_path.as_posix(), workspace_id="w1")
    assert report["reingestion_required"] is False
    assert "dataset-1" in report["dataset_ids"]
