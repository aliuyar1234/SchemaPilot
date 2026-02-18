"""Retention purge helpers for workspace-scoped artifact cleanup."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PurgeExecution:
    """Deterministic purge execution summary."""

    scanned_count: int
    deleted_count: int
    deleted_paths: list[str]
    cutoff_epoch: float
    dry_run: bool


def purge_workspace_artifacts(
    *,
    workspace_id: str,
    purge_root: str,
    retention_days: int,
    dry_run: bool,
) -> PurgeExecution:
    """Purge workspace artifacts older than retention cutoff."""
    if retention_days <= 0:
        raise ValueError("retention_days_must_be_positive")
    base = Path(purge_root)
    if not base.exists():
        raise ValueError("purge_root_missing")
    if not base.is_dir():
        raise ValueError("purge_root_not_directory")

    cutoff_epoch = time.time() - float(retention_days * 86400)
    candidate_roots = [
        base / "bronze" / workspace_id,
        base / "silver" / workspace_id,
        base / "gold" / workspace_id,
        base / "documents" / workspace_id,
    ]
    scanned = 0
    to_delete: list[Path] = []
    for root in candidate_roots:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            scanned += 1
            if path.stat().st_mtime <= cutoff_epoch:
                to_delete.append(path)

    deleted_paths = sorted(path.relative_to(base).as_posix() for path in to_delete)
    if not dry_run:
        for path in to_delete:
            path.unlink(missing_ok=True)
        _remove_empty_directories(candidate_roots)

    return PurgeExecution(
        scanned_count=scanned,
        deleted_count=len(deleted_paths),
        deleted_paths=deleted_paths,
        cutoff_epoch=cutoff_epoch,
        dry_run=dry_run,
    )


def _remove_empty_directories(roots: list[Path]) -> None:
    for root in roots:
        if not root.exists():
            continue
        for path in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
            try:
                path.rmdir()
            except OSError:
                continue
