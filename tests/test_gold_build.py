from __future__ import annotations

import json
from pathlib import Path

from backend.workers.gold import build_gold_snapshot


def test_gold_build_writes_manifest_and_pointer_fail_closed(tmp_path: Path) -> None:
    rows = [{"amount": 10}, {"amount": 20}]
    result = build_gold_snapshot(
        workspace_id="w1",
        model_name="finance",
        silver_rows=rows,
        metric_field="amount",
        output_root=tmp_path.as_posix(),
        snapshot_id="gold-snap-1",
        allow_publish=False,
    )
    assert Path(result.data_path).exists()
    assert Path(result.semantic_manifest_path).exists()
    pointer = json.loads(Path(result.published_pointer_path).read_text(encoding="utf-8"))
    assert pointer["snapshot_id"] is None
