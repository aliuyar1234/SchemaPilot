from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AuditOutboxEvent
from backend.shared_domain.audit_outbox import dispatch_audit_outbox_batch, enqueue_audit_outbox_event
from backend.shared_domain.audit_sinks import AuditSinkError, JsonlAuditSink
from backend.shared_domain.db import Base, get_engine, get_session_factory


def _session_factory(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'audit_outbox.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    return get_session_factory(database_url)


def test_dispatch_outbox_writes_jsonl_and_marks_rows_sent(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    session: Session = session_factory()
    try:
        enqueue_audit_outbox_event(
            session,
            service="gateway",
            workspace_id="w1",
            audit_event_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
            payload={
                "audit_event_id": "01AAAAAAAAAAAAAAAAAAAAAAAA",
                "workspace_id": "w1",
                "event_type": "gateway.query",
            },
        )
        session.commit()
    finally:
        session.close()

    sink_path = tmp_path / "audit" / "outbox.jsonl"
    result = dispatch_audit_outbox_batch(
        session_factory=session_factory,
        sink=JsonlAuditSink(target_path=sink_path),
        service="gateway",
        max_batch=10,
        max_attempts=3,
    )
    assert result.attempted == 1
    assert result.sent == 1
    assert result.failed == 0
    assert result.pending == 0
    lines = sink_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_type"] == "gateway.query"

    verify_session: Session = session_factory()
    try:
        row = verify_session.execute(select(AuditOutboxEvent)).scalar_one()
        assert row.status == "sent"
        assert row.attempt_count == 1
        assert row.last_error is None
    finally:
        verify_session.close()


def test_dispatch_outbox_bounds_retries_and_marks_failed(tmp_path: Path) -> None:
    class FailingSink:
        def emit(self, event: dict[str, object]) -> None:  # noqa: ARG002
            raise AuditSinkError("audit_sink_unavailable")

    session_factory = _session_factory(tmp_path)
    session: Session = session_factory()
    try:
        enqueue_audit_outbox_event(
            session,
            service="control_plane",
            workspace_id="w2",
            audit_event_id="01BBBBBBBBBBBBBBBBBBBBBBBB",
            payload={
                "audit_event_id": "01BBBBBBBBBBBBBBBBBBBBBBBB",
                "workspace_id": "w2",
                "event_type": "workspace.created",
            },
        )
        session.commit()
    finally:
        session.close()

    result = dispatch_audit_outbox_batch(
        session_factory=session_factory,
        sink=FailingSink(),
        service="control_plane",
        max_batch=10,
        max_attempts=1,
    )
    assert result.attempted == 1
    assert result.sent == 0
    assert result.failed == 1
    assert result.pending == 0

    verify_session: Session = session_factory()
    try:
        row = verify_session.execute(select(AuditOutboxEvent)).scalar_one()
        assert row.status == "failed"
        assert row.attempt_count == 1
        assert row.last_error == "audit_sink_unavailable"
    finally:
        verify_session.close()
