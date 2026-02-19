"""Deterministic DB dump discovery connector."""

from __future__ import annotations

import hashlib
from pathlib import Path


def discover(scope: dict[str, object]) -> list[dict[str, object]]:
    """Discover SQL/dump files from a root directory."""
    root_path = str(scope.get("root_path", "")).strip()
    if not root_path:
        raise ValueError("root_path_required")
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("root_path_not_found")
    suffixes_raw = scope.get("suffixes", [".sql", ".dump", ".dmp"])
    suffixes = (
        [str(item).strip().lower() for item in suffixes_raw if str(item).strip()]
        if isinstance(suffixes_raw, list)
        else [".sql", ".dump", ".dmp"]
    )
    if not suffixes:
        suffixes = [".sql", ".dump", ".dmp"]
    discovered: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in suffixes:
            continue
        stat = path.stat()
        discovered.append(
            {
                "path": path.as_posix(),
                "dataset_family": _dataset_family(path.name),
                "size_bytes": int(stat.st_size),
                "mtime_epoch": float(stat.st_mtime),
                "content_hash_sample": _sample_hash(path),
            }
        )
    return discovered


def _dataset_family(name: str) -> str:
    normalized = name.lower()
    if "postgres" in normalized or normalized.endswith(".sql"):
        return "postgres_dump"
    if "mysql" in normalized:
        return "mysql_dump"
    return "db_dump"


def _sample_hash(path: Path, sample_bytes: int = 4096) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        hasher.update(handle.read(sample_bytes))
    return hasher.hexdigest()

