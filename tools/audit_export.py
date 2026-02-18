#!/usr/bin/env python3
"""Export append-only audit rows to deterministic JSONL format."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_engine, get_session_factory


def export_audit_jsonl(*, database_url: str, output_path: Path) -> dict[str, int]:
    """Write deterministic JSONL export of audit events and access decisions."""
    engine = get_engine(database_url)
    AuditEvent.metadata.create_all(bind=engine)
    session_factory = get_session_factory(database_url)
    rows: list[dict[str, object]] = []
    with session_factory() as session:
        events = (
            session.execute(select(AuditEvent).order_by(AuditEvent.audit_event_id)).scalars().all()
        )
        decisions = (
            session.execute(select(AccessDecision).order_by(AccessDecision.decision_id))
            .scalars()
            .all()
        )
        for event in events:
            rows.append(
                {
                    "schema_version": "1",
                    "record_type": "audit_event",
                    "audit_event_id": event.audit_event_id,
                    "workspace_id": event.workspace_id,
                    "actor_id": event.actor_id,
                    "event_type": event.event_type,
                    "event_json": event.event_json,
                    "correlation_id": event.correlation_id,
                }
            )
        for decision in decisions:
            rows.append(
                {
                    "schema_version": "1",
                    "record_type": "access_decision",
                    "decision_id": decision.decision_id,
                    "workspace_id": decision.workspace_id,
                    "actor_id": decision.actor_id,
                    "request_context_json": decision.request_context_json,
                    "resources_json": decision.resources_json,
                    "result": decision.result,
                    "applied_filters_json": decision.applied_filters_json,
                    "applied_masks_json": decision.applied_masks_json,
                    "audit_event_id": decision.audit_event_id,
                }
            )
    rows.sort(
        key=lambda row: (
            str(row.get("record_type", "")),
            str(row.get("audit_event_id", row.get("decision_id", ""))),
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "audit_event_count": sum(1 for row in rows if row["record_type"] == "audit_event"),
        "access_decision_count": sum(1 for row in rows if row["record_type"] == "access_decision"),
        "total_count": len(rows),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db"),
    )
    parser.add_argument(
        "--output",
        default="runtime/audit/export.jsonl",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_path = Path(args.output)
    stats = export_audit_jsonl(database_url=str(args.database_url), output_path=output_path)
    event_count = stats["audit_event_count"]
    decision_count = stats["access_decision_count"]
    print(
        "PASS audit export written:"
        f" {output_path.as_posix()} (events={event_count}, decisions={decision_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
