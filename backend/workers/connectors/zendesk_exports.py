"""Deterministic Zendesk export discovery helper for worker-native source type support."""

from __future__ import annotations

from pathlib import Path


def discover_zendesk_exports(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover Zendesk CSV exports from a local export root."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists():
        raise ValueError("root_path_not_found")
    discovered: list[dict[str, object]] = []
    for path in sorted(root.glob("zendesk_*.csv")):
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": "zendesk",
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": "",
            }
        )
    return discovered
