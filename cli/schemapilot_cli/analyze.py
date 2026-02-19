"""Workspace analytics for denials, review backlog, runs, and run steps."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AccessDecision, AuditEvent, AuditOutboxEvent
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.failure_codes import resolve_failure_metadata
from backend.shared_domain.metadata_models import ReviewTask, RunRecord, RunStepRecord

ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_CHAR_TO_VALUE = {char: index for index, char in enumerate(ULID_ALPHABET)}


def analyze_workspace(*, database_url: str, workspace_id: str) -> dict[str, object]:
    """Build deterministic analytics payload for one workspace."""
    session_factory = get_session_factory(database_url)
    session: Session = session_factory()
    try:
        tasks = (
            session.execute(select(ReviewTask).where(ReviewTask.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        runs = (
            session.execute(select(RunRecord).where(RunRecord.workspace_id == workspace_id))
            .scalars()
            .all()
        )
        run_steps = (
            session.execute(select(RunStepRecord).where(RunStepRecord.workspace_id == workspace_id))
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
        event_ids = sorted({decision.audit_event_id for decision in decisions})
        events = (
            session.execute(select(AuditEvent).where(AuditEvent.audit_event_id.in_(event_ids)))
            .scalars()
            .all()
            if event_ids
            else []
        )
        outbox_rows = (
            session.execute(
                select(AuditOutboxEvent).where(
                    (AuditOutboxEvent.workspace_id == workspace_id)
                    | (AuditOutboxEvent.workspace_id.is_(None))
                )
            )
            .scalars()
            .all()
        )
    finally:
        session.close()

    event_by_id = {event.audit_event_id: event for event in events}
    denial_reason_counter: Counter[str] = Counter()
    for decision in decisions:
        if decision.result != "deny":
            continue
        event = event_by_id.get(decision.audit_event_id)
        reason = "unknown"
        if event is not None and isinstance(event.event_json, dict):
            reason = str(event.event_json.get("reason", "unknown"))
        denial_reason_counter[reason] += 1

    by_priority = Counter(str(task.priority) for task in tasks)
    by_status = Counter(str(task.status) for task in tasks)
    blocking_open = sum(
        1 for task in tasks if bool(task.blocking) and str(task.status) in {"open", "in_review"}
    )
    runs_by_status = Counter(str(run.status) for run in runs)
    runs_by_type = Counter(str(run.run_type) for run in runs)
    step_status_counts = Counter(str(step.status) for step in run_steps)
    step_failure_codes = Counter(str(step.error_code) for step in run_steps if step.error_code)
    step_failure_taxonomy: Counter[str] = Counter()
    step_failure_categories: Counter[str] = Counter()
    for step in run_steps:
        if not step.error_code:
            continue
        details = step.details_json if isinstance(step.details_json, dict) else {}
        failure_message = str(details.get("error")) if details.get("error") is not None else None
        metadata = resolve_failure_metadata(
            details=details,
            legacy_error_code=step.error_code,
            message=failure_message,
        )
        if metadata is None:
            continue
        step_failure_taxonomy[str(metadata["failure_code"])] += 1
        step_failure_categories[str(metadata["failure_category"])] += 1
    outbox_by_service = Counter(str(row.service) for row in outbox_rows if row.status == "pending")
    top_denials = [
        {"reason": reason, "count": int(count)}
        for reason, count in sorted(
            denial_reason_counter.items(),
            key=lambda item: (-int(item[1]), str(item[0])),
        )
    ]
    oldest_blockers = _oldest_blocking_tasks(tasks, now_epoch=int(time.time()))
    suggested_actions = _suggested_actions(
        top_denials=top_denials,
        blocking_tasks=oldest_blockers,
        failure_categories=step_failure_categories,
        workspace_id=workspace_id,
    )

    return {
        "workspace_id": workspace_id,
        "generated_at_epoch": int(time.time()),
        "policy_denials": {
            "total": int(sum(denial_reason_counter.values())),
            "by_reason": top_denials,
        },
        "review_queue": {
            "total_tasks": int(len(tasks)),
            "blocking_open_tasks": int(blocking_open),
            "oldest_blocking_tasks": oldest_blockers,
            "by_priority": dict(sorted((key, int(value)) for key, value in by_priority.items())),
            "by_status": dict(sorted((key, int(value)) for key, value in by_status.items())),
        },
        "runs": {
            "total": int(len(runs)),
            "by_status": dict(
                sorted((status, int(count)) for status, count in runs_by_status.items())
            ),
            "by_type": dict(
                sorted((run_type, int(count)) for run_type, count in runs_by_type.items())
            ),
        },
        "run_steps": {
            "total": int(len(run_steps)),
            "by_status": dict(
                sorted((status, int(count)) for status, count in step_status_counts.items())
            ),
            "failed_by_error_code": dict(
                sorted((code, int(count)) for code, count in step_failure_codes.items())
            ),
            "failed_by_failure_code": dict(
                sorted((code, int(count)) for code, count in step_failure_taxonomy.items())
            ),
            "failed_by_failure_category": dict(
                sorted((code, int(count)) for code, count in step_failure_categories.items())
            ),
        },
        "audit_outbox": {
            "pending_total": int(sum(outbox_by_service.values())),
            "pending_by_service": dict(
                sorted((service, int(count)) for service, count in outbox_by_service.items())
            ),
        },
        "suggested_next_actions": suggested_actions,
        "slo_export_hint": (
            f"schemapilot slo export --workspace {workspace_id} --format json"
        ),
    }


def _oldest_blocking_tasks(
    tasks: Sequence[ReviewTask], *, now_epoch: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for task in tasks:
        if not bool(task.blocking):
            continue
        status = str(task.status)
        if status not in {"open", "in_review"}:
            continue
        created_epoch = _ulid_epoch_seconds(str(task.task_id))
        age_seconds = max(now_epoch - created_epoch, 0)
        rows.append(
            {
                "task_id": str(task.task_id),
                "status": status,
                "priority": str(task.priority),
                "subject_ref": str(task.subject_ref),
                "age_seconds": int(age_seconds),
            }
        )
    return sorted(
        rows,
        key=lambda item: (-_to_int(item.get("age_seconds")), str(item.get("task_id", ""))),
    )[:5]


def _suggested_actions(
    *,
    top_denials: list[dict[str, object]],
    blocking_tasks: list[dict[str, object]],
    failure_categories: Counter[str],
    workspace_id: str,
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    if blocking_tasks:
        actions.append(
            {
                "kind": "review_queue",
                "message": "Resolve oldest blocking review tasks first.",
                "hint": f"schemapilot review-summary --workspace {workspace_id}",
            }
        )
    if top_denials:
        top_reason = str(top_denials[0].get("reason", "unknown"))
        remediation = {
            "missing_or_invalid_auth_token": "schemapilot doctor",
            "dataset_not_allowed": (
                f"schemapilot slo export --workspace {workspace_id} --format json"
            ),
            "dataset_workspace_mismatch": "Check source/workspace mapping and rerun discover.",
            "approval_required": "Open review queue and approve blocking governance tasks.",
        }.get(top_reason, "Inspect diagnostics bundle and runbook failure taxonomy.")
        actions.append(
            {
                "kind": "denial_hotspot",
                "message": f"Top denial reason: {top_reason}",
                "hint": remediation,
            }
        )
    if failure_categories:
        top_failure = sorted(
            failure_categories.items(),
            key=lambda item: (-int(item[1]), str(item[0])),
        )[0][0]
        actions.append(
            {
                "kind": "run_failures",
                "message": f"Top failure category: {top_failure}",
                "hint": "See docs/runbook/FAILURE_CODES.md for operator remediation anchors.",
            }
        )
    if not actions:
        actions.append(
            {
                "kind": "healthy",
                "message": "No immediate blockers detected.",
                "hint": f"schemapilot slo export --workspace {workspace_id} --format json",
            }
        )
    return actions


def _ulid_epoch_seconds(value: str) -> int:
    normalized = value.strip().upper()
    if len(normalized) < 10:
        return int(datetime.now(tz=UTC).timestamp())
    timestamp = 0
    for char in normalized[:10]:
        digit = ULID_CHAR_TO_VALUE.get(char)
        if digit is None:
            return int(datetime.now(tz=UTC).timestamp())
        timestamp = (timestamp * 32) + digit
    return int(timestamp // 1000)


def _to_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default
