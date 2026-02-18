"""Durable outbox queue for audit sink delivery."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.shared_domain.audit_models import AuditOutboxEvent
from backend.shared_domain.audit_sinks import AuditSink, AuditSinkError
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.observability import (
    increment_audit_sink_delivery,
    observe_audit_sink_delivery_latency,
    set_audit_outbox_backlog,
)


@dataclass(frozen=True)
class AuditOutboxDispatchResult:
    """Summary of one outbox dispatch cycle."""

    attempted: int
    sent: int
    failed: int
    pending: int


def enqueue_audit_outbox_event(
    session: Session,
    *,
    service: str,
    workspace_id: str | None,
    audit_event_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Persist an outbox event in the same transaction as audit writes."""
    outbox_event = AuditOutboxEvent(
        outbox_event_id=new_ulid(),
        service=service,
        workspace_id=workspace_id,
        audit_event_id=audit_event_id,
        payload_json=payload,
        status="pending",
        attempt_count=0,
        last_error=None,
    )
    session.add(outbox_event)
    session.flush()
    return {
        "outbox_event_id": outbox_event.outbox_event_id,
        "service": outbox_event.service,
        "workspace_id": outbox_event.workspace_id,
        "audit_event_id": outbox_event.audit_event_id,
        "status": outbox_event.status,
        "attempt_count": outbox_event.attempt_count,
    }


def dispatch_audit_outbox_batch(
    *,
    session_factory: sessionmaker[Session],
    sink: AuditSink,
    service: str,
    max_batch: int,
    max_attempts: int,
) -> AuditOutboxDispatchResult:
    """Attempt delivery for pending outbox rows with bounded retries."""
    session = session_factory()
    attempted = 0
    sent = 0
    failed = 0
    try:
        rows = (
            session.execute(
                select(AuditOutboxEvent)
                .where(
                    AuditOutboxEvent.service == service,
                    AuditOutboxEvent.status == "pending",
                    AuditOutboxEvent.attempt_count < max_attempts,
                )
                .order_by(AuditOutboxEvent.outbox_event_id)
                .limit(max_batch)
            )
            .scalars()
            .all()
        )
        for row in rows:
            attempted += 1
            started = perf_counter()
            try:
                sink.emit(dict(row.payload_json))
                row.status = "sent"
                row.attempt_count += 1
                row.last_error = None
                sent += 1
                increment_audit_sink_delivery(service=service, result="sent")
                observe_audit_sink_delivery_latency(
                    service=service,
                    result="sent",
                    latency_ms=(perf_counter() - started) * 1000.0,
                )
            except (AuditSinkError, OSError, TimeoutError) as exc:
                row.attempt_count += 1
                row.last_error = str(exc)
                failed += 1
                if row.attempt_count >= max_attempts:
                    row.status = "failed"
                increment_audit_sink_delivery(service=service, result="failed")
                observe_audit_sink_delivery_latency(
                    service=service,
                    result="failed",
                    latency_ms=(perf_counter() - started) * 1000.0,
                )
        session.commit()
        pending = _count_pending_outbox_rows(session=session, service=service, max_attempts=max_attempts)
        set_audit_outbox_backlog(service=service, count=pending)
        return AuditOutboxDispatchResult(
            attempted=attempted,
            sent=sent,
            failed=failed,
            pending=pending,
        )
    finally:
        session.close()


def _count_pending_outbox_rows(*, session: Session, service: str, max_attempts: int) -> int:
    pending_count = session.execute(
        select(func.count())
        .select_from(AuditOutboxEvent)
        .where(
            AuditOutboxEvent.service == service,
            AuditOutboxEvent.status == "pending",
            AuditOutboxEvent.attempt_count < max_attempts,
        )
    ).scalar_one()
    return int(pending_count)
