"""SLO/SLA export helpers (CLI-first, deterministic ordering)."""

from __future__ import annotations

import csv
import io
import time
from collections import Counter
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import (
    CatalogDataset,
    CatalogSource,
    ReviewTask,
    RunRecord,
    TargetDbState,
    TargetDbSyncCursor,
)

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_CHAR_TO_VALUE = {char: index for index, char in enumerate(ULID_ALPHABET)}
OPEN_REVIEW_STATUSES = {"open", "in_review"}
SENSITIVE_EXPORT_ROLES = {"platform_admin", "data_steward"}


def export_slo_snapshot(
    *,
    database_url: str,
    workspace_id: str,
    actor_role: str = "platform_admin",
    include_sensitive_breakdown: bool = True,
) -> dict[str, object]:
    """Build deterministic SLO export payload for one workspace."""

    normalized_role = actor_role.strip().lower()
    if include_sensitive_breakdown and normalized_role not in SENSITIVE_EXPORT_ROLES:
        raise PermissionError("role_not_allowed_for_sensitive_slo_export")

    session_factory = get_session_factory(database_url)
    session: Session = session_factory()
    try:
        sources = (
            session.execute(select(CatalogSource).where(CatalogSource.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        datasets = (
            session.execute(
                select(CatalogDataset).where(CatalogDataset.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        runs = (
            session.execute(select(RunRecord).where(RunRecord.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        review_tasks = (
            session.execute(select(ReviewTask).where(ReviewTask.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        decisions = (
            session.execute(
                select(AccessDecision).where(AccessDecision.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        sync_cursors = (
            session.execute(
                select(TargetDbSyncCursor).where(TargetDbSyncCursor.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        target_state = session.get(TargetDbState, workspace_id)
        event_ids = sorted({decision.audit_event_id for decision in decisions})
        events = (
            session.execute(select(AuditEvent).where(AuditEvent.audit_event_id.in_(event_ids)))
            .scalars()
            .all()
            if event_ids
            else []
        )
    finally:
        session.close()

    now_epoch = int(time.time())
    source_by_id = {source.source_id: source for source in sources}
    sync_by_dataset = {row.dataset_id: row for row in sync_cursors}
    latest_discover_epoch = _max_ulid_epoch(
        run.run_id
        for run in runs
        if str(run.run_type) == "discover" and str(run.status) == "succeeded"
    )
    freshness_rows = _build_freshness_rows(
        datasets=datasets,
        source_by_id=source_by_id,
        sync_by_dataset=sync_by_dataset,
        latest_discover_epoch=latest_discover_epoch,
        now_epoch=now_epoch,
    )
    queue = _build_queue_snapshot(runs=runs, now_epoch=now_epoch)
    denial_rows = _build_denial_rows(decisions=decisions, events=events)
    review = _build_review_snapshot(tasks=review_tasks, now_epoch=now_epoch)
    sync_lag = _build_sync_lag_snapshot(target_state=target_state, now_epoch=now_epoch)

    payload = {
        "schema_version": "slo.v1",
        "workspace_id": workspace_id,
        "generated_at_epoch": now_epoch,
        "data_freshness": freshness_rows,
        "run_queue": queue,
        "denials": denial_rows,
        "review_latency": review,
        "sync_lag": sync_lag,
        "role": normalized_role,
        "sensitive_breakdown": include_sensitive_breakdown,
    }
    if include_sensitive_breakdown:
        return payload
    return _redact_sensitive_breakdown(payload)


def render_slo_csv(payload: dict[str, object]) -> str:
    """Render SLO payload as deterministic CSV rows."""

    rows: list[tuple[str, str, str, str]] = []
    queue = payload.get("run_queue", {})
    if isinstance(queue, dict):
        rows.append(("run_queue", "depth", "all", _str_value(queue.get("depth"))))
        rows.append(
            (
                "run_queue",
                "oldest_queued_age_seconds",
                "all",
                _str_value(queue.get("oldest_queued_age_seconds")),
            )
        )
    for item in _list_dict(payload.get("data_freshness")):
        dataset_id = str(item.get("dataset_id", "unknown"))
        rows.append(
            (
                "data_freshness",
                "freshness_seconds",
                dataset_id,
                _str_value(item.get("freshness_seconds")),
            )
        )
    for item in _list_dict(payload.get("denials")):
        reason = str(item.get("reason", "unknown"))
        rows.append(
            (
                "denials",
                "denial_count",
                reason,
                _str_value(item.get("count")),
            )
        )
    review = payload.get("review_latency", {})
    if isinstance(review, dict):
        rows.append(
            (
                "review_latency",
                "blocking_open_count",
                "all",
                _str_value(review.get("blocking_open_count")),
            )
        )
        rows.append(
            (
                "review_latency",
                "oldest_blocking_age_seconds",
                "all",
                _str_value(review.get("oldest_blocking_age_seconds")),
            )
        )
    sync_lag = payload.get("sync_lag", {})
    if isinstance(sync_lag, dict):
        rows.append(
            (
                "sync_lag",
                "lag_seconds",
                "all",
                _str_value(sync_lag.get("lag_seconds")),
            )
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "metric", "dimension", "value"])
    for section, metric, dimension, value in sorted(rows):
        writer.writerow([section, metric, dimension, value])
    return buffer.getvalue()


def _build_freshness_rows(
    *,
    datasets: Sequence[CatalogDataset],
    source_by_id: dict[str, CatalogSource],
    sync_by_dataset: dict[str, TargetDbSyncCursor],
    latest_discover_epoch: int | None,
    now_epoch: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for dataset in sorted(datasets, key=lambda item: (item.source_id, item.dataset_id)):
        cursor = sync_by_dataset.get(dataset.dataset_id)
        last_sync_run_id = (
            str(cursor.last_run_id) if cursor is not None and cursor.last_run_id else None
        )
        last_sync_epoch = (
            _ulid_timestamp_epoch(last_sync_run_id) if last_sync_run_id is not None else None
        )
        effective_epoch = last_sync_epoch if last_sync_epoch is not None else latest_discover_epoch
        freshness_seconds = (
            max(now_epoch - effective_epoch, 0) if effective_epoch is not None else None
        )
        source = source_by_id.get(dataset.source_id)
        rows.append(
            {
                "dataset_id": dataset.dataset_id,
                "source_id": dataset.source_id,
                "source_type": str(source.source_type) if source is not None else "unknown",
                "freshness_seconds": freshness_seconds,
                "last_sync_epoch": effective_epoch,
                "last_sync_run_id": last_sync_run_id,
                "sync_status": str(cursor.last_status) if cursor is not None else "unknown",
            }
        )
    return rows


def _build_queue_snapshot(*, runs: Sequence[RunRecord], now_epoch: int) -> dict[str, object]:
    queued = [run for run in runs if str(run.status) == "queued"]
    queued_ages = [
        max(now_epoch - created_epoch, 0)
        for created_epoch in (_ulid_timestamp_epoch(run.run_id) for run in queued)
        if created_epoch is not None
    ]
    queued_by_type = Counter(str(run.run_type) for run in queued)
    return {
        "depth": len(queued),
        "oldest_queued_age_seconds": max(queued_ages) if queued_ages else None,
        "by_run_type": dict(
            sorted((run_type, int(count)) for run_type, count in queued_by_type.items())
        ),
    }


def _build_denial_rows(
    *, decisions: Sequence[AccessDecision], events: Sequence[AuditEvent]
) -> list[dict[str, object]]:
    event_by_id = {event.audit_event_id: event for event in events}
    denial_counts: Counter[str] = Counter()
    for decision in decisions:
        if str(decision.result) != "deny":
            continue
        event = event_by_id.get(decision.audit_event_id)
        reason = "unknown"
        if event is not None and isinstance(event.event_json, dict):
            reason = str(event.event_json.get("reason", "unknown"))
        denial_counts[reason] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in sorted(
            denial_counts.items(), key=lambda item: (-int(item[1]), str(item[0]))
        )
    ]


def _build_review_snapshot(*, tasks: Sequence[ReviewTask], now_epoch: int) -> dict[str, object]:
    open_blocking = [
        task for task in tasks if bool(task.blocking) and str(task.status) in OPEN_REVIEW_STATUSES
    ]
    task_rows: list[dict[str, object]] = []
    ages: list[int] = []
    for task in sorted(open_blocking, key=lambda row: (str(row.priority), str(row.task_id))):
        created_epoch = _ulid_timestamp_epoch(task.task_id)
        age_seconds = max(now_epoch - created_epoch, 0) if created_epoch is not None else None
        if age_seconds is not None:
            ages.append(age_seconds)
        task_rows.append(
            {
                "task_id": task.task_id,
                "priority": task.priority,
                "status": task.status,
                "age_seconds": age_seconds,
            }
        )
    return {
        "blocking_open_count": len(open_blocking),
        "oldest_blocking_age_seconds": max(ages) if ages else None,
        "tasks": task_rows,
    }


def _build_sync_lag_snapshot(
    *, target_state: TargetDbState | None, now_epoch: int
) -> dict[str, object]:
    if target_state is None:
        return {
            "active_target_db_id": None,
            "health_status": "unknown",
            "last_successful_sync_epoch": None,
            "lag_seconds": None,
        }
    last_successful_sync_epoch = (
        int(target_state.last_successful_sync_epoch)
        if target_state.last_successful_sync_epoch is not None
        else None
    )
    lag_seconds = (
        max(now_epoch - last_successful_sync_epoch, 0)
        if last_successful_sync_epoch is not None
        else None
    )
    return {
        "active_target_db_id": target_state.active_target_db_id,
        "health_status": str(target_state.health_status),
        "last_successful_sync_epoch": last_successful_sync_epoch,
        "lag_seconds": lag_seconds,
    }


def _ulid_timestamp_epoch(value: str | None) -> int | None:
    normalized = str(value or "").strip().upper()
    if len(normalized) < 10:
        return None
    timestamp_ms = 0
    for char in normalized[:10]:
        digit = ULID_CHAR_TO_VALUE.get(char)
        if digit is None:
            return None
        timestamp_ms = (timestamp_ms * 32) + digit
    return int(timestamp_ms / 1000)


def _max_ulid_epoch(values: Iterable[str]) -> int | None:
    best: int | None = None
    for value in values:
        epoch = _ulid_timestamp_epoch(str(value))
        if epoch is None:
            continue
        if best is None or epoch > best:
            best = epoch
    return best


def _list_dict(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _str_value(value: object) -> str:
    return "" if value is None else str(value)


def _redact_sensitive_breakdown(payload: dict[str, object]) -> dict[str, object]:
    denials = _list_dict(payload.get("denials"))
    data_freshness = _list_dict(payload.get("data_freshness"))
    review_latency = payload.get("review_latency", {})
    review_count = 0
    if isinstance(review_latency, dict):
        review_count = _coerce_int(review_latency.get("blocking_open_count", 0))
    denial_total = sum(_coerce_int(row.get("count", 0)) for row in denials)
    redacted = {
        "schema_version": payload.get("schema_version", "slo.v1"),
        "workspace_id": payload.get("workspace_id"),
        "generated_at_epoch": payload.get("generated_at_epoch"),
        "role": payload.get("role"),
        "sensitive_breakdown": False,
        "data_freshness": {
            "dataset_count": len(data_freshness),
            "known_freshness_count": sum(
                1 for row in data_freshness if row.get("freshness_seconds") is not None
            ),
        },
        "run_queue": payload.get("run_queue", {}),
        "denials": {
            "total": denial_total,
            "by_reason": [{"reason": "redacted", "count": denial_total}] if denials else [],
        },
        "review_latency": {"blocking_open_count": review_count},
        "sync_lag": payload.get("sync_lag", {}),
    }
    return redacted


def _coerce_int(value: object) -> int:
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
            return 0
    return 0
