"""Run scheduling helpers for fail-closed cron-like execution."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import GovernancePolicy, RunRecord

RUN_SCHEDULE_POLICY_TYPE = "run_schedule"
_MINUTE_CRON = re.compile(r"^\*/(\d{1,4}) \* \* \* \*$")


def validate_schedule_expression(expression: str) -> int:
    """Validate supported schedule expression and return interval seconds."""
    normalized = expression.strip().lower()
    if normalized == "@hourly":
        return 3600
    if normalized == "@daily":
        return 86400
    match = _MINUTE_CRON.fullmatch(normalized)
    if match is None:
        raise ValueError("invalid_schedule_expression")
    minutes = int(match.group(1))
    if minutes <= 0 or minutes > 1440:
        raise ValueError("invalid_schedule_expression")
    return minutes * 60


def create_run_schedule(
    session: Session,
    *,
    workspace_id: str,
    run_type: str,
    schedule_expression: str,
    enabled: bool,
    actor_id: str,
) -> dict[str, object]:
    """Create a run schedule represented as a governance policy row."""
    interval_seconds = validate_schedule_expression(schedule_expression)
    schedule_id = new_ulid()
    now_epoch = int(time.time())
    payload = {
        "schedule_id": schedule_id,
        "workspace_id": workspace_id,
        "run_type": run_type,
        "schedule_expression": schedule_expression,
        "interval_seconds": interval_seconds,
        "enabled": enabled,
        "next_run_epoch": now_epoch + interval_seconds if enabled else None,
        "created_by": actor_id,
    }
    session.add(
        GovernancePolicy(
            policy_id=schedule_id,
            workspace_id=workspace_id,
            policy_type=RUN_SCHEDULE_POLICY_TYPE,
            definition_ref=json.dumps(payload, sort_keys=True),
            status="active",
        )
    )
    session.flush()
    return payload


def list_run_schedules(session: Session, *, workspace_id: str) -> list[dict[str, object]]:
    """List run schedules for a workspace."""
    rows = (
        session.execute(
            select(GovernancePolicy)
            .where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == RUN_SCHEDULE_POLICY_TYPE,
                GovernancePolicy.status == "active",
            )
            .order_by(GovernancePolicy.policy_id)
        )
        .scalars()
        .all()
    )
    schedules: list[dict[str, object]] = []
    for row in rows:
        schedules.append(_parse_schedule_payload(row.definition_ref, fallback_id=row.policy_id))
    return schedules


def enqueue_due_scheduled_runs(
    session: Session,
    *,
    now_epoch: int | None = None,
) -> list[dict[str, object]]:
    """Create queued run records for all due schedules and advance next run timestamp."""
    now = int(time.time()) if now_epoch is None else now_epoch
    rows = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.policy_type == RUN_SCHEDULE_POLICY_TYPE,
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .all()
    )
    created: list[dict[str, object]] = []
    for row in rows:
        payload = _parse_schedule_payload(row.definition_ref, fallback_id=row.policy_id)
        if not bool(payload.get("enabled", False)):
            continue
        next_run_epoch_raw = payload.get("next_run_epoch")
        if not isinstance(next_run_epoch_raw, int):
            continue
        if next_run_epoch_raw > now:
            continue
        run = RunRecord(
            run_id=new_ulid(),
            workspace_id=str(payload.get("workspace_id", row.workspace_id)),
            run_type=str(payload.get("run_type", "discover")),
            status="queued",
            input_refs_json={
                "source": "scheduler",
                "schedule_id": str(payload.get("schedule_id", row.policy_id)),
            },
            output_refs_json={},
        )
        session.add(run)
        interval_seconds = int(payload.get("interval_seconds", 60))
        payload["next_run_epoch"] = now + max(interval_seconds, 60)
        row.definition_ref = json.dumps(payload, sort_keys=True)
        created.append(
            {
                "run_id": run.run_id,
                "workspace_id": run.workspace_id,
                "run_type": run.run_type,
                "schedule_id": str(payload.get("schedule_id", row.policy_id)),
            }
        )
    session.flush()
    return created


def _parse_schedule_payload(definition_ref: str, *, fallback_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(definition_ref)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if "schedule_id" not in payload:
        payload["schedule_id"] = fallback_id
    return payload
