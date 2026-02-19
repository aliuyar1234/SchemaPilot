"""Deterministic source snapshot mirror manifests."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable
from pathlib import Path


def normalize_snapshot_entries(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Normalize and sort source snapshot entries deterministically."""
    normalized: list[dict[str, object]] = []
    for row in rows:
        path = str(row.get("path", "")).strip()
        if not path:
            continue
        normalized.append(
            {
                "path": path,
                "size_bytes": _as_int(row.get("size_bytes"), default=0),
                "mtime_epoch": _as_float(row.get("mtime_epoch"), default=0.0),
                "content_hash_sample": str(row.get("content_hash_sample", "")).strip(),
                "dataset_family": str(row.get("dataset_family", "")).strip(),
            }
        )
    return sorted(normalized, key=lambda item: str(item["path"]))


def build_source_snapshot_manifest(
    *,
    workspace_id: str,
    source_id: str,
    source_type: str,
    root_path: str,
    cursor_before: str,
    cursor_after: str,
    rows: Iterable[dict[str, object]],
    strict_mode: bool,
    generated_epoch: int | None = None,
) -> dict[str, object]:
    """Build deterministic source snapshot manifest payload."""
    entries = normalize_snapshot_entries(rows)
    canonical = {
        "manifest_version": "v1",
        "workspace_id": workspace_id,
        "source_id": source_id,
        "source_type": source_type,
        "root_path": root_path,
        "cursor_after": cursor_after,
        "strict_mode": strict_mode,
        "entries": entries,
        "entry_count": len(entries),
    }
    snapshot_checksum = _checksum(canonical)
    generated = int(time.time()) if generated_epoch is None else int(generated_epoch)
    return {
        **canonical,
        "cursor_before": cursor_before,
        "snapshot_checksum": snapshot_checksum,
        "generated_epoch": generated,
    }


def persist_source_snapshot_manifest(
    *,
    storage_root: str,
    manifest: dict[str, object],
) -> dict[str, object]:
    """Persist source snapshot manifest and return materialized pointers."""
    workspace_id = str(manifest.get("workspace_id", "")).strip()
    source_id = str(manifest.get("source_id", "")).strip()
    snapshot_checksum = str(manifest.get("snapshot_checksum", "")).strip()
    if not workspace_id or not source_id or not snapshot_checksum:
        raise ValueError("invalid_source_snapshot_manifest")
    base = Path(storage_root) / "source_mirror" / workspace_id / source_id
    snapshots = base / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots / f"{snapshot_checksum}.json"
    latest_path = base / "latest.json"
    rendered = json.dumps(manifest, indent=2, sort_keys=True)
    snapshot_path.write_text(rendered + "\n", encoding="utf-8")
    latest_path.write_text(rendered + "\n", encoding="utf-8")
    return {
        "snapshot_checksum": snapshot_checksum,
        "snapshot_path": snapshot_path.as_posix(),
        "latest_path": latest_path.as_posix(),
        "snapshot_uri": f"source-mirror://{workspace_id}/{source_id}/{snapshot_checksum}",
    }


def load_latest_source_snapshot_manifest(
    *,
    storage_root: str,
    workspace_id: str,
    source_id: str,
) -> dict[str, object] | None:
    """Load latest manifest for a workspace source if available."""
    latest_path = Path(storage_root) / "source_mirror" / workspace_id / source_id / "latest.json"
    if not latest_path.exists():
        return None
    try:
        body = json.loads(latest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    return {str(key): value for key, value in body.items()}


def source_snapshot_changed(
    *,
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> bool:
    """Return whether snapshot checksum changed from previous state."""
    current_checksum = str(current.get("snapshot_checksum", "")).strip()
    previous_checksum = (
        str(previous.get("snapshot_checksum", "")).strip() if isinstance(previous, dict) else ""
    )
    return bool(current_checksum and current_checksum != previous_checksum)


def _checksum(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _as_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default
