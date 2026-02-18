"""Gold publish pointer persistence and rollback helpers."""

from __future__ import annotations

import json
from pathlib import Path


def load_latest_gold_pointer(*, workspace_id: str, storage_root: str) -> dict[str, object] | None:
    """Load latest published gold pointer if present."""
    latest_path = _pointer_dir(workspace_id=workspace_id, storage_root=storage_root) / "latest.json"
    if not latest_path.exists():
        return None
    raw = json.loads(latest_path.read_text(encoding="utf-8"))
    return _normalize_pointer(raw)


def publish_gold_pointer(
    *,
    workspace_id: str,
    build_id: str,
    snapshot_id: str,
    model_name: str,
    storage_root: str,
) -> dict[str, object]:
    """Publish a new gold pointer and append to history."""
    pointer: dict[str, object] = {
        "workspace_id": workspace_id,
        "build_id": build_id,
        "snapshot_id": snapshot_id,
        "model_name": model_name,
    }
    pointer_root = _pointer_dir(workspace_id=workspace_id, storage_root=storage_root)
    pointer_root.mkdir(parents=True, exist_ok=True)
    latest_path = pointer_root / "latest.json"
    latest_path.write_text(json.dumps(pointer, indent=2, sort_keys=True), encoding="utf-8")

    history = _load_history(workspace_id=workspace_id, storage_root=storage_root)
    if not history or history[-1].get("build_id") != build_id:
        history.append(pointer)
        _write_history(workspace_id=workspace_id, storage_root=storage_root, history=history)
    return pointer


def rollback_gold_pointer(
    *, workspace_id: str, build_id: str | None, storage_root: str
) -> dict[str, object]:
    """Rollback to requested build ID or previous history entry."""
    history = _load_history(workspace_id=workspace_id, storage_root=storage_root)
    if not history:
        raise ValueError("No gold publish history available for rollback.")

    current = history[-1]
    target: dict[str, object] | None = None
    if build_id:
        for item in reversed(history):
            if str(item.get("build_id")) == build_id:
                target = item
                break
        if target is None:
            raise ValueError("Requested rollback target was not found in publish history.")
    elif len(history) >= 2:
        target = history[-2]
    else:
        target = history[-1]

    latest_path = _pointer_dir(workspace_id=workspace_id, storage_root=storage_root) / "latest.json"
    latest_path.write_text(json.dumps(target, indent=2, sort_keys=True), encoding="utf-8")
    if not history or history[-1] != target:
        history.append(target)
        _write_history(workspace_id=workspace_id, storage_root=storage_root, history=history)
    return {"current": current, "rolled_back_to": target}


def _pointer_dir(*, workspace_id: str, storage_root: str) -> Path:
    return Path(storage_root) / "gold" / workspace_id / "_published"


def _load_history(*, workspace_id: str, storage_root: str) -> list[dict[str, object]]:
    history_path = (
        _pointer_dir(workspace_id=workspace_id, storage_root=storage_root) / "history.json"
    )
    if not history_path.exists():
        return []
    raw = json.loads(history_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    return [_normalize_pointer(item) for item in raw]


def _write_history(
    *, workspace_id: str, storage_root: str, history: list[dict[str, object]]
) -> None:
    history_path = (
        _pointer_dir(workspace_id=workspace_id, storage_root=storage_root) / "history.json"
    )
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_pointer(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return {
        "workspace_id": str(raw.get("workspace_id", "")),
        "build_id": str(raw.get("build_id", "")),
        "snapshot_id": str(raw.get("snapshot_id", "")),
        "model_name": str(raw.get("model_name", "")),
    }
