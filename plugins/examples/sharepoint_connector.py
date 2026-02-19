"""Reference SharePoint/OneDrive connector (snapshot + delta cursor mode)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def plugin_id() -> str:
    """Return stable plugin identifier."""
    return "sharepoint_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover SharePoint-exported files from a local mirror root.

    This v1 connector models Graph snapshot/delta behavior deterministically:
    - local mirror path is scanned read-only
    - cursor_state.cursor (or cursor_state.delta_cursor) is treated as a delta watermark
    - only newer rows are returned when a cursor exists
    """
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    cursor_state_raw = scope.get("cursor_state", {})
    cursor_state = cursor_state_raw if isinstance(cursor_state_raw, dict) else {}
    previous_cursor = str(
        cursor_state.get("delta_cursor", cursor_state.get("cursor", ""))
    ).strip()
    include_extensions = _normalize_extensions(scope.get("include_extensions"))
    discovered: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if include_extensions and path.suffix.lower() not in include_extensions:
            continue
        token = _cursor_token(path)
        if previous_cursor and token <= previous_cursor:
            continue
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": "sharepoint",
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": _sample_hash(path),
                "delta_token": token,
            }
        )
    return discovered


def _normalize_extensions(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    normalized: set[str] = set()
    for item in value:
        extension = str(item).strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        normalized.add(extension)
    return normalized


def _cursor_token(path: Path) -> str:
    stat = path.stat()
    return f"{float(stat.st_mtime):020.3f}:{path.as_posix()}"


def _sample_hash(path: Path, sample_bytes: int = 4096) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        hasher.update(handle.read(sample_bytes))
    return hasher.hexdigest()
