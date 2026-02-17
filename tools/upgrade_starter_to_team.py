#!/usr/bin/env python3
"""Starter -> Team upgrade drill helper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--workspace-id", required=True)
    return parser.parse_args()


def run_upgrade(*, storage_root: str, workspace_id: str) -> dict[str, object]:
    root = Path(storage_root)
    bronze_root = root / "bronze" / workspace_id
    manifests = list(bronze_root.rglob("manifest.json"))
    dataset_ids = sorted({path.parts[-4] for path in manifests}) if manifests else []

    team_meta = root / "team_upgrade" / workspace_id
    team_meta.mkdir(parents=True, exist_ok=True)
    report = {
        "workspace_id": workspace_id,
        "dataset_ids": dataset_ids,
        "reingestion_required": False,
        "status": "upgraded_stub",
    }
    (team_meta / "upgrade_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def main() -> int:
    args = parse_args()
    report = run_upgrade(storage_root=args.storage_root, workspace_id=args.workspace_id)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
