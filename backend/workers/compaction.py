"""Deterministic small-file compaction helpers for JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path


def compact_json_files(
    *,
    input_files: list[str],
    output_file: str,
) -> dict[str, object]:
    """Compact multiple JSON array files into one deterministic file."""
    unique_inputs = sorted({Path(path).as_posix() for path in input_files})
    rows: list[object] = []
    for path_str in unique_inputs:
        path = Path(path_str)
        if not path.exists():
            raise ValueError(f"missing_compaction_input:{path.as_posix()}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"invalid_compaction_payload:{path.as_posix()}")
        rows.extend(payload)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "input_count": len(unique_inputs),
        "output_path": output_path.as_posix(),
        "row_count": len(rows),
    }
