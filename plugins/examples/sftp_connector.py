"""Reference SFTP connector plugin (read-only strict snapshot mode)."""

from __future__ import annotations

from pathlib import Path

from backend.shared_domain.streaming_io import sample_sha256


def plugin_id() -> str:
    """Return stable plugin identifier."""
    return "sftp_connector"


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover SFTP-exported files from a local mirror path."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    suffix = str(scope.get("suffix", ".csv")).strip() or ".csv"
    discovered: list[dict[str, object]] = []
    for path in sorted(root.rglob(f"*{suffix}")):
        if not path.is_file():
            continue
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": "sftp",
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": _sample_hash(path),
            }
        )
    return discovered


def _sample_hash(path: Path, sample_bytes: int = 4096) -> str:
    return sample_sha256(path, sample_bytes=sample_bytes)
