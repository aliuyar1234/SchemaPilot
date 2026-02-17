"""Read-only filesystem discovery connector."""

from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass
from pathlib import Path


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
) -> list[DiscoveredFile]:
    """Discover files under root path in read-only mode."""
    root = Path(root_path)
    excluded = exclude_globs or []
    discovered: list[DiscoveredFile] = []
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        rel = file_path.relative_to(root).as_posix()
        if not any(_match_pattern(rel, pattern) for pattern in include_globs):
            continue
        if any(_match_pattern(rel, pattern) for pattern in excluded):
            continue
        stat = file_path.stat()
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
    hasher = hashlib.sha256()
    with file_path.open("rb") as handle:
        hasher.update(handle.read(sample_bytes))
    return hasher.hexdigest()


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
