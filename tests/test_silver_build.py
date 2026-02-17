from __future__ import annotations

from pathlib import Path

from backend.workers.silver import build_silver_snapshot


def test_silver_build_normalizes_and_writes_crosswalk(tmp_path: Path) -> None:
    rows = [{"invoice_id": " 1 ", "amount": "10.5"}, {"invoice_id": "2", "amount": "20"}]
    result = build_silver_snapshot(
        workspace_id="w1",
        entity_name="invoices",
        source_records=rows,
        natural_key_fields=["invoice_id"],
        output_root=tmp_path.as_posix(),
        snapshot_id="snap-1",
    )
    assert Path(result.data_path).exists()
    assert Path(result.crosswalk_path).exists()
