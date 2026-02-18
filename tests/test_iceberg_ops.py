from __future__ import annotations

import json
from pathlib import Path

from backend.workers.gold import build_gold_snapshot
from backend.workers.iceberg_ops import run_iceberg_maintenance_hooks


def test_run_iceberg_maintenance_hooks_writes_report_when_enabled(tmp_path: Path) -> None:
    report_path = run_iceberg_maintenance_hooks(
        workspace_id="w1",
        snapshot_id="s1",
        output_root=tmp_path.as_posix(),
        enabled=True,
    )
    assert report_path is not None
    payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert payload["status"] == "applied"
    assert payload["operations"][0]["name"] == "expire_snapshots"


def test_gold_build_can_emit_maintenance_report(tmp_path: Path) -> None:
    result = build_gold_snapshot(
        workspace_id="w1",
        model_name="finance",
        silver_rows=[{"amount": 10}],
        metric_field="amount",
        output_root=tmp_path.as_posix(),
        snapshot_id="snap-1",
        allow_publish=True,
        run_maintenance_hooks_enabled=True,
    )
    assert result.maintenance_report_path is not None
    assert Path(result.maintenance_report_path).exists()
