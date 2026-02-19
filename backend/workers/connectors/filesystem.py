"""Read-only filesystem discovery connector."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from backend.shared_domain.streaming_io import sample_sha256


@dataclass(frozen=True)
class DiscoveredFile:
    """Discovered file metadata."""

    path: str
    size_bytes: int
    mtime_epoch: float
    content_hash_sample: str
    dataset_family: str


def discover_files(
    *,
    root_path: str,
    include_globs: list[str],
    exclude_globs: list[str] | None = None,
    max_files: int = 10_000,
    max_total_bytes: int = 1_000_000_000,
) -> list[DiscoveredFile]:
    """Discover files under root path in read-only mode."""
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Filesystem root does not exist or is not a directory: {root_path}")
    if not include_globs:
        raise ValueError("include_globs must not be empty.")
    excluded = exclude_globs or []
    discovered: list[DiscoveredFile] = []
    total_bytes = 0
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        rel = file_path.relative_to(root).as_posix()
        if not any(_match_pattern(rel, pattern) for pattern in include_globs):
            continue
        if any(_match_pattern(rel, pattern) for pattern in excluded):
            continue
        stat = file_path.stat()
        total_bytes += int(stat.st_size)
        if len(discovered) + 1 > max(max_files, 1):
            raise ValueError("filesystem_discovery_backpressure_limit_exceeded")
        if total_bytes > max(max_total_bytes, 1):
            raise ValueError("filesystem_discovery_backpressure_limit_exceeded")
        discovered.append(
            DiscoveredFile(
                path=file_path.as_posix(),
                size_bytes=stat.st_size,
                mtime_epoch=stat.st_mtime,
                content_hash_sample=_sample_hash(file_path),
                dataset_family=_infer_dataset_family(file_path.name),
            )
        )
    return discovered


def _sample_hash(file_path: Path, sample_bytes: int = 8192) -> str:
    return sample_sha256(file_path, sample_bytes=sample_bytes)


def _infer_dataset_family(filename: str) -> str:
    normalized = filename.lower()
    token = normalized.split(".")[0]
    for separator in ("-", "_", " "):
        if separator in token:
            return token.split(separator)[0]
    return token


def _match_pattern(value: str, pattern: str) -> bool:
    if fnmatch.fnmatch(value, pattern):
        return True
    if pattern.startswith("**/"):
        return fnmatch.fnmatch(value, pattern[3:])
    return False
