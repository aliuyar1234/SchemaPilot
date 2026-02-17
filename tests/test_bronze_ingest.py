from __future__ import annotations

import json
from pathlib import Path

from backend.workers.bronze import ingest_file_to_bronze


def test_bronze_ingest_writes_manifest_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text("id,amount\n1,10\n", encoding="utf-8")

    first = ingest_file_to_bronze(
        workspace_id="w1",
        source_id="s1",
        dataset_id="d1",
        source_file=source.as_posix(),
        storage_root=(tmp_path / "storage").as_posix(),
        run_id="run1",
    )
    second = ingest_file_to_bronze(
        workspace_id="w1",
        source_id="s1",
        dataset_id="d1",
        source_file=source.as_posix(),
        storage_root=(tmp_path / "storage").as_posix(),
        run_id="run2",
    )

    assert first.content_hash == second.content_hash
    assert Path(first.raw_path).exists()
    assert Path(second.raw_path).exists()
    manifest = json.loads(Path(second.manifest_path).read_text(encoding="utf-8"))
    assert manifest["content_hash"] == first.content_hash
