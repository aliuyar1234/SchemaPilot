"""Optional MySQL CDC-style connector (deterministic local fixture mode)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def plugin_id() -> str:
    """Return stable plugin id."""
    return "mysql_cdc_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Read deterministic JSONL binlog events and emit rows newer than cursor."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    cursor_state_raw = scope.get("cursor_state", {})
    cursor_state = cursor_state_raw if isinstance(cursor_state_raw, dict) else {}
    previous_pos = str(cursor_state.get("binlog_pos", "")).strip()
    events_path = root / "mysql_cdc_events.jsonl"
    if not events_path.exists():
        return []
    discovered: list[dict[str, object]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        position = str(event.get("binlog_pos", "")).strip()
        if not position:
            continue
        if previous_pos and position <= previous_pos:
            continue
        table = str(event.get("table", "cdc_event")).strip() or "cdc_event"
        event_path = f"{events_path.as_posix()}#{position}"
        discovered.append(
            {
                "path": event_path,
                "dataset_family": table,
                "size_bytes": len(line.encode("utf-8")),
                "mtime_epoch": float(event.get("epoch", 0.0))
                if isinstance(event.get("epoch"), (int, float))
                else 0.0,
                "content_hash_sample": _sample_hash(line=line),
            }
        )
    return sorted(discovered, key=lambda row: str(row.get("path", "")))


def _sample_hash(*, line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()
