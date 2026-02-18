from __future__ import annotations

import json
from pathlib import Path

from backend.workers.compaction import compact_json_files


def test_compact_json_files_merges_rows_deterministically(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(json.dumps([{"id": 1}, {"id": 2}], sort_keys=True), encoding="utf-8")
    second.write_text(json.dumps([{"id": 3}], sort_keys=True), encoding="utf-8")
    output = tmp_path / "out" / "compact.json"
    result = compact_json_files(
        input_files=[second.as_posix(), first.as_posix()],
        output_file=output.as_posix(),
    )
    assert result["input_count"] == 2
    assert result["row_count"] == 3
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["id"] == 1
    assert payload[2]["id"] == 3


def test_compact_json_files_fails_for_missing_input(tmp_path: Path) -> None:
    output = tmp_path / "compact.json"
    try:
        compact_json_files(
            input_files=[(tmp_path / "missing.json").as_posix()], output_file=output.as_posix()
        )
    except ValueError as exc:
        assert "missing_compaction_input" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing_compaction_input")
