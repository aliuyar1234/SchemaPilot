"""Reference IMAP connector plugin (incremental mailbox snapshot)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def plugin_id() -> str:
    """Return stable plugin identifier."""
    return "imap_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover EML files from mailbox export root with cursor-based incrementality."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    cursor_state_raw = scope.get("cursor_state", {})
    cursor_state = cursor_state_raw if isinstance(cursor_state_raw, dict) else {}
    previous_cursor = str(cursor_state.get("cursor", "")).strip()
    include_attachments = bool(scope.get("include_attachments", False))
    discovered: list[dict[str, object]] = []
    candidates: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".eml":
            candidates.append((_cursor_token(path), path))
        elif include_attachments and path.suffix.lower() in {".pdf", ".txt", ".csv"}:
            candidates.append((_cursor_token(path), path))
    for token, path in candidates:
        if previous_cursor and token <= previous_cursor:
            continue
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": "imap",
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": _sample_hash(path),
            }
        )
    return discovered


def _cursor_token(path: Path) -> str:
    stat = path.stat()
    return f"{float(stat.st_mtime):020.3f}:{path.as_posix()}"


def _sample_hash(path: Path, sample_bytes: int = 4096) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        hasher.update(handle.read(sample_bytes))
    return hasher.hexdigest()

