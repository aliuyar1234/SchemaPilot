"""Workspace analytics for denials, review backlog, runs, and run steps."""

from __future__ import annotations

import time
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AccessDecision, AuditEvent, AuditOutboxEvent
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import ReviewTask, RunRecord, RunStepRecord


def analyze_workspace(*, database_url: str, workspace_id: str) -> dict[str, object]:
    """Build deterministic analytics payload for one workspace."""
    session_factory = get_session_factory(database_url)
    session: Session = session_factory()
    try:
        tasks = (
            session.execute(
                select(ReviewTask).where(ReviewTask.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        runs = (
            session.execute(
                select(RunRecord).where(RunRecord.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        run_steps = (
            session.execute(
                select(RunStepRecord).where(RunStepRecord.workspace_id == workspace_id)
            )
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
            session.execute(
                select(AuditEvent).where(AuditEvent.audit_event_id.in_(event_ids))
            )
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
        1
        for task in tasks
        if bool(task.blocking) and str(task.status) in {"open", "in_review"}
    )
    runs_by_status = Counter(str(run.status) for run in runs)
    runs_by_type = Counter(str(run.run_type) for run in runs)
    step_status_counts = Counter(str(step.status) for step in run_steps)
    step_failure_codes = Counter(str(step.error_code) for step in run_steps if step.error_code)
    outbox_by_service = Counter(str(row.service) for row in outbox_rows if row.status == "pending")

    return {
        "workspace_id": workspace_id,
        "generated_at_epoch": int(time.time()),
        "policy_denials": {
            "total": int(sum(denial_reason_counter.values())),
            "by_reason": [
                {"reason": reason, "count": int(count)}
                for reason, count in sorted(
                    denial_reason_counter.items(),
                    key=lambda item: (-int(item[1]), str(item[0])),
                )
            ],
        },
        "review_queue": {
            "total_tasks": int(len(tasks)),
            "blocking_open_tasks": int(blocking_open),
            "by_priority": dict(sorted((key, int(value)) for key, value in by_priority.items())),
            "by_status": dict(sorted((key, int(value)) for key, value in by_status.items())),
        },
        "runs": {
            "total": int(len(runs)),
            "by_status": dict(
                sorted((status, int(count)) for status, count in runs_by_status.items())
            ),
            "by_type": dict(sorted((run_type, int(count)) for run_type, count in runs_by_type.items())),
        },
        "run_steps": {
            "total": int(len(run_steps)),
            "by_status": dict(
                sorted((status, int(count)) for status, count in step_status_counts.items())
            ),
            "failed_by_error_code": dict(
                sorted((code, int(count)) for code, count in step_failure_codes.items())
            ),
        },
        "audit_outbox": {
            "pending_total": int(sum(outbox_by_service.values())),
            "pending_by_service": dict(
                sorted((service, int(count)) for service, count in outbox_by_service.items())
            ),
        },
    }
