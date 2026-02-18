"""Optional deterministic maintenance hooks for Iceberg/Trino profiles."""

from __future__ import annotations

import json
from pathlib import Path


def run_iceberg_maintenance_hooks(
    *,
    workspace_id: str,
    snapshot_id: str,
    output_root: str,
    enabled: bool,
) -> str | None:
    """Write a deterministic maintenance report when hooks are enabled."""
    if not enabled:
        return None
    report_root = Path(output_root) / "gold" / workspace_id / "_maintenance"
    report_root.mkdir(parents=True, exist_ok=True)
    report_path = report_root / f"{snapshot_id}.json"
    payload = {
        "workspace_id": workspace_id,
        "snapshot_id": snapshot_id,
        "operations": [
            {"name": "expire_snapshots", "status": "simulated"},
            {"name": "rewrite_manifests", "status": "simulated"},
        ],
        "status": "applied",
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return report_path.as_posix()
