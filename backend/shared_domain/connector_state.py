"""Deterministic connector cursor/state contract helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def load_connector_state(
    *, storage_root: str, workspace_id: str, source_id: str
) -> dict[str, object]:
    """Load connector cursor/state for one workspace source."""
    state_path = _state_path(
        storage_root=storage_root, workspace_id=workspace_id, source_id=source_id
    )
    if not state_path.exists():
        return {}
    try:
        parsed = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): value for key, value in parsed.items()}


def save_connector_state(
    *, storage_root: str, workspace_id: str, source_id: str, state: dict[str, object]
) -> str:
    """Persist connector cursor/state in deterministic JSON form."""
    payload = {str(key): value for key, value in state.items()}
    payload.setdefault("updated_epoch", int(time.time()))
    state_path = _state_path(
        storage_root=storage_root, workspace_id=workspace_id, source_id=source_id
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return state_path.as_posix()


def next_cursor_from_discovery_rows(
    rows: list[dict[str, Any]], *, previous_cursor: str | None = None
) -> str:
    """Compute monotonic deterministic cursor watermark from discovery rows."""
    candidates: list[str] = []
    for row in rows:
        path = str(row.get("path", "")).strip()
        mtime = (
            float(row.get("mtime_epoch", 0.0))
            if isinstance(row.get("mtime_epoch"), (int, float))
            else 0.0
        )
        candidates.append(f"{mtime:020.3f}:{path}")
    if previous_cursor:
        candidates.append(previous_cursor)
    if not candidates:
        return previous_cursor or ""
    return max(candidates)


def _state_path(*, storage_root: str, workspace_id: str, source_id: str) -> Path:
    return Path(storage_root) / "connector_state" / workspace_id / source_id / "state.json"
