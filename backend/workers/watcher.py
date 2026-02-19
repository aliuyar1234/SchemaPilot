"""Poll-based source watcher for deterministic discover-triggering."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.connector_state import (
    load_connector_state,
    next_cursor_from_discovery_rows,
)
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import CatalogSource, RunRecord
from backend.shared_domain.source_mirror import (
    build_source_snapshot_manifest,
    load_latest_source_snapshot_manifest,
    source_snapshot_changed,
)
from backend.workers.connectors.dropzone import discover_dropzone_files
from backend.workers.connectors.filesystem import discover_files

WATCH_SOURCE_TYPES = {"filesystem", "dropzone"}


def enqueue_source_watcher_runs(
    session: Session,
    *,
    storage_root: str,
    strict_ingest: bool,
) -> dict[str, object]:
    """Detect source snapshot changes and enqueue discover runs."""
    sources = (
        session.execute(
            select(CatalogSource)
            .where(CatalogSource.status == "active")
            .order_by(CatalogSource.workspace_id, CatalogSource.source_id)
        )
        .scalars()
        .all()
    )
    changed_by_workspace: dict[str, list[dict[str, object]]] = {}
    failures: list[dict[str, object]] = []
    evaluated = 0

    for source in sources:
        if source.source_type not in WATCH_SOURCE_TYPES:
            continue
        evaluated += 1
        scope = source.scope_json if isinstance(source.scope_json, dict) else {}
        root_path = str(scope.get("root_path", "")).strip()
        if not root_path:
            failures.append(
                {
                    "workspace_id": source.workspace_id,
                    "source_id": source.source_id,
                    "reason": "missing_root_path",
                }
            )
            continue
        try:
            if source.source_type == "filesystem":
                include_globs = _string_list(scope.get("include_globs"), default=["**/*.csv"])
                exclude_globs = _string_list(scope.get("exclude_globs"), default=[])
                discovered = discover_files(
                    root_path=root_path,
                    include_globs=include_globs,
                    exclude_globs=exclude_globs,
                )
            else:
                include_globs = _string_list(scope.get("include_globs"), default=[])
                exclude_globs = _string_list(scope.get("exclude_globs"), default=[])
                required_files = _string_list(scope.get("required_files"), default=[])
                discovered = discover_dropzone_files(
                    root_path=root_path,
                    include_globs=include_globs or None,
                    exclude_globs=exclude_globs or None,
                    required_files=required_files or None,
                )
        except Exception as exc:
            failures.append(
                {
                    "workspace_id": source.workspace_id,
                    "source_id": source.source_id,
                    "reason": "discovery_failed",
                    "error": str(exc),
                }
            )
            continue
        state = load_connector_state(
            storage_root=storage_root,
            workspace_id=source.workspace_id,
            source_id=source.source_id,
        )
        cursor_before = str(state.get("cursor", ""))
        cursor_after = next_cursor_from_discovery_rows(
            [{"path": item.path, "mtime_epoch": item.mtime_epoch} for item in discovered],
            previous_cursor=cursor_before or None,
        )
        current_manifest = build_source_snapshot_manifest(
            workspace_id=source.workspace_id,
            source_id=source.source_id,
            source_type=source.source_type,
            root_path=root_path,
            cursor_before=cursor_before,
            cursor_after=cursor_after,
            rows=[
                {
                    "path": item.path,
                    "size_bytes": item.size_bytes,
                    "mtime_epoch": item.mtime_epoch,
                    "content_hash_sample": item.content_hash_sample,
                    "dataset_family": item.dataset_family,
                }
                for item in discovered
            ],
            strict_mode=strict_ingest,
            generated_epoch=int(time.time()),
        )
        previous_manifest = load_latest_source_snapshot_manifest(
            storage_root=storage_root,
            workspace_id=source.workspace_id,
            source_id=source.source_id,
        )
        if not source_snapshot_changed(previous=previous_manifest, current=current_manifest):
            continue
        changed_by_workspace.setdefault(source.workspace_id, []).append(
            {
                "source_id": source.source_id,
                "source_type": source.source_type,
                "snapshot_checksum": str(current_manifest.get("snapshot_checksum", "")),
                "entry_count": _as_int(current_manifest.get("entry_count"), default=0),
            }
        )

    created_runs: list[dict[str, object]] = []
    for workspace_id in sorted(changed_by_workspace):
        has_discover_pending = (
            session.execute(
                select(RunRecord)
                .where(
                    RunRecord.workspace_id == workspace_id,
                    RunRecord.run_type == "discover",
                    RunRecord.status.in_(("queued", "running")),
                )
                .limit(1)
            )
            .scalars()
            .first()
            is not None
        )
        if has_discover_pending:
            continue
        run = RunRecord(
            run_id=new_ulid(),
            workspace_id=workspace_id,
            run_type="discover",
            status="queued",
            input_refs_json={
                "trigger": "watcher",
                "changed_sources": changed_by_workspace[workspace_id],
            },
            output_refs_json={},
        )
        session.add(run)
        created_runs.append(
            {
                "workspace_id": workspace_id,
                "run_id": run.run_id,
                "changed_source_count": len(changed_by_workspace[workspace_id]),
            }
        )
    session.flush()
    return {
        "evaluated_sources": evaluated,
        "changed_workspace_count": len(changed_by_workspace),
        "enqueued_run_count": len(created_runs),
        "created_runs": created_runs,
        "failures": failures,
    }


def _string_list(value: object, *, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    parsed = [str(item).strip() for item in value if str(item).strip()]
    return parsed if parsed else list(default)


def _as_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default
