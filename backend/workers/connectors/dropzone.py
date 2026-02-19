"""Dropzone connector for deterministic export-folder ingestion."""

from __future__ import annotations

from pathlib import Path

from backend.workers.connectors.filesystem import DiscoveredFile, discover_files

DEFAULT_DROPZONE_INCLUDE_GLOBS = [
    "**/*.csv",
    "**/*.json",
    "**/*.xlsx",
    "**/*.xls",
    "**/*.zip",
]
DEFAULT_DROPZONE_EXCLUDE_GLOBS = ["**/~$*", "**/.DS_Store", "**/Thumbs.db"]


def discover_dropzone_files(
    *,
    root_path: str,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    required_files: list[str] | None = None,
    max_files: int = 20_000,
    max_total_bytes: int = 5_000_000_000,
) -> list[DiscoveredFile]:
    """Discover files in export dropzone with strict required-file checks."""
    discovered = discover_files(
        root_path=root_path,
        include_globs=include_globs or DEFAULT_DROPZONE_INCLUDE_GLOBS,
        exclude_globs=exclude_globs or DEFAULT_DROPZONE_EXCLUDE_GLOBS,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
    )
    required = _normalize_required_files(required_files)
    if required:
        root = Path(root_path).resolve()
        discovered_rel = {
            _relative_path(root=root, absolute_path=item.path)
            for item in discovered
        }
        missing = sorted(required.difference(discovered_rel))
        if missing:
            raise ValueError(f"dropzone_required_files_missing:{','.join(missing)}")
    return discovered


def _normalize_required_files(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    normalized = {str(item).strip().replace("\\", "/") for item in values if str(item).strip()}
    return {item.lstrip("./") for item in normalized if item}


def _relative_path(*, root: Path, absolute_path: str) -> str:
    target = Path(absolute_path).resolve()
    try:
        value = target.relative_to(root).as_posix()
    except ValueError:
        value = target.as_posix()
    return value.lstrip("./")
