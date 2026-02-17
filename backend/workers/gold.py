"""Gold semantic build helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoldBuildResult:
    """Gold build output paths."""

    snapshot_id: str
    data_path: str
    semantic_manifest_path: str
    published_pointer_path: str


def build_gold_snapshot(
    *,
    workspace_id: str,
    model_name: str,
    silver_rows: list[dict[str, object]],
    metric_field: str,
    output_root: str,
    snapshot_id: str,
    allow_publish: bool,
) -> GoldBuildResult:
    """Build a simple semantic aggregate and publish pointer fail-closed."""
    total = 0.0
    for row in silver_rows:
        value = row.get(metric_field, 0)
        if isinstance(value, (int, float)):
            total += float(value)
    aggregate = [{"metric": f"sum_{metric_field}", "value": total}]

    snapshot_root = (
        Path(output_root) / "gold" / workspace_id / model_name / "snapshots" / snapshot_id
    )
    snapshot_root.mkdir(parents=True, exist_ok=True)
    data_path = snapshot_root / "metrics.json"
    data_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")

    semantic_manifest = {
        "manifest_version": "1.0.0",
        "model_name": model_name,
        "snapshot_id": snapshot_id,
        "metrics": [{"name": f"sum_{metric_field}", "grain": "global"}],
    }
    semantic_root = Path(output_root) / "gold" / workspace_id / "semantic_manifest" / "v1"
    semantic_root.mkdir(parents=True, exist_ok=True)
    semantic_manifest_path = semantic_root / "manifest.json"
    semantic_manifest_path.write_text(
        json.dumps(semantic_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    published_pointer = Path(output_root) / "gold" / workspace_id / "_published" / "latest.json"
    published_pointer.parent.mkdir(parents=True, exist_ok=True)
    if allow_publish:
        published_pointer.write_text(
            json.dumps({"snapshot_id": snapshot_id, "model_name": model_name}, indent=2),
            encoding="utf-8",
        )
    elif not published_pointer.exists():
        published_pointer.write_text(
            json.dumps({"snapshot_id": None, "model_name": model_name}, indent=2),
            encoding="utf-8",
        )

    return GoldBuildResult(
        snapshot_id=snapshot_id,
        data_path=data_path.as_posix(),
        semantic_manifest_path=semantic_manifest_path.as_posix(),
        published_pointer_path=published_pointer.as_posix(),
    )
