"""Reference Google Drive snapshot connector plugin (read-only strict)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def plugin_id() -> str:
    """Return stable plugin identifier."""
    return "google_drive_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover exported Google Drive files from a local snapshot folder."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    include_prefix = str(scope.get("filename_prefix", "gdrive_")).strip() or "gdrive_"
    discovered: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not path.name.startswith(include_prefix):
            continue
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": "google_drive",
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": _sample_hash(path),
            }
        )
    return discovered


def _sample_hash(path: Path, sample_bytes: int = 4096) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        hasher.update(handle.read(sample_bytes))
    return hasher.hexdigest()

