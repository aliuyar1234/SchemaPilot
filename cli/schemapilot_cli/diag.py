"""Redacted diagnostics bundle generation for operator support."""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.config import load_settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.failure_codes import resolve_failure_metadata
from backend.shared_domain.metadata_models import RunRecord, RunStepRecord
from backend.shared_domain.policy_packs import load_policy_packs
from backend.shared_domain.secrets import redact_secrets
from cli.schemapilot_cli.analyze import analyze_workspace


def generate_diag_bundle(
    *,
    workspace_id: str,
    database_url: str,
    output_path: str,
    config_path: str | None = None,
    max_rows: int = 200,
) -> dict[str, object]:
    """Create a deterministic redacted support bundle zip for one workspace."""
    settings = load_settings(config_path)
    analysis = analyze_workspace(database_url=database_url, workspace_id=workspace_id)
    session_factory = get_session_factory(database_url)
    session: Session = session_factory()
    try:
        runs = (
            session.execute(
                select(RunRecord)
                .where(RunRecord.workspace_id == workspace_id)
                .order_by(RunRecord.run_id.desc())
                .limit(max_rows)
            )
            .scalars()
            .all()
        )
        run_steps = (
            session.execute(
                select(RunStepRecord)
                .where(RunStepRecord.workspace_id == workspace_id)
                .order_by(RunStepRecord.run_id.desc(), RunStepRecord.step_order)
                .limit(max_rows * 8)
            )
            .scalars()
            .all()
        )
        events = (
            session.execute(
                select(AuditEvent)
                .where(AuditEvent.workspace_id == workspace_id)
                .order_by(AuditEvent.audit_event_id.desc())
                .limit(max_rows)
            )
            .scalars()
            .all()
        )
        decisions = (
            session.execute(
                select(AccessDecision)
                .where(AccessDecision.workspace_id == workspace_id)
                .order_by(AccessDecision.decision_id.desc())
                .limit(max_rows)
            )
            .scalars()
            .all()
        )
    finally:
        session.close()

    event_reason_by_id: dict[str, str] = {}
    for event in events:
        reason = "unknown"
        if isinstance(event.event_json, dict):
            reason = str(event.event_json.get("reason", "unknown"))
        event_reason_by_id[event.audit_event_id] = reason

    payloads = {
        "meta/summary.json": _json_bytes(
            {
                "workspace_id": workspace_id,
                "generated_at_epoch": int(time.time()),
                "bundle_version": "v1",
                "counts": {
                    "runs": len(runs),
                    "run_steps": len(run_steps),
                    "audit_events": len(events),
                    "access_decisions": len(decisions),
                },
                "pack_versions": _collect_pack_versions(),
                "manifest_hashes": _collect_manifest_hashes(),
            }
        ),
        "config/settings_redacted.json": _json_bytes(settings.to_redacted_dict()),
        "analysis/workspace_analysis.json": _json_bytes(analysis),
        "runs/recent_runs.json": _json_bytes(
            [
                {
                    "run_id": row.run_id,
                    "workspace_id": row.workspace_id,
                    "run_type": row.run_type,
                    "status": row.status,
                    "input_refs": row.input_refs_json,
                    "output_refs": row.output_refs_json,
                }
                for row in runs
            ]
        ),
        "runs/recent_run_steps.json": _json_bytes(
            [_serialize_run_step(row) for row in run_steps]
        ),
        "audit/audit_excerpt.json": _json_bytes(
            {
                "events": [
                    {
                        "audit_event_id": row.audit_event_id,
                        "workspace_id": row.workspace_id,
                        "actor_id": row.actor_id,
                        "event_type": row.event_type,
                        "correlation_id": row.correlation_id,
                        "reason": event_reason_by_id.get(row.audit_event_id, "unknown"),
                    }
                    for row in events
                ],
                "access_decisions": [
                    {
                        "decision_id": row.decision_id,
                        "workspace_id": row.workspace_id,
                        "actor_id": row.actor_id,
                        "result": row.result,
                        "audit_event_id": row.audit_event_id,
                        "reason": event_reason_by_id.get(row.audit_event_id, "unknown"),
                    }
                    for row in decisions
                ],
            }
        ),
    }

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(payloads.items(), key=lambda item: item[0]):
            archive.writestr(path, content)
    return {
        "status": "ok",
        "workspace_id": workspace_id,
        "bundle_path": destination.as_posix(),
        "entry_count": len(payloads),
    }


def _json_bytes(payload: object) -> bytes:
    serialized = json.dumps(payload, indent=2, sort_keys=True, default=str)
    redacted = redact_secrets(serialized)
    return (redacted + "\n").encode("utf-8")


def _serialize_run_step(row: RunStepRecord) -> dict[str, object]:
    details = dict(row.details_json) if isinstance(row.details_json, dict) else {}
    failure_message = str(details.get("error")) if details.get("error") is not None else None
    metadata = resolve_failure_metadata(
        details=details,
        legacy_error_code=row.error_code,
        message=failure_message,
    )
    return {
        "run_step_id": row.run_step_id,
        "run_id": row.run_id,
        "step_key": row.step_key,
        "step_order": row.step_order,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "error_code": row.error_code,
        "failure_code": metadata["failure_code"] if metadata is not None else None,
        "failure_category": metadata["failure_category"] if metadata is not None else None,
        "operator_hint_ref": metadata["operator_hint_ref"] if metadata is not None else None,
        "failure_code_version": metadata["failure_code_version"] if metadata is not None else None,
        "evidence_bundle_uri": row.evidence_bundle_uri,
        "started_epoch": row.started_epoch,
        "finished_epoch": row.finished_epoch,
        "duration_ms": row.duration_ms,
        "depends_on": row.depends_on_json,
        "details": details,
    }


def _collect_pack_versions() -> list[dict[str, str]]:
    versions: list[dict[str, str]] = []
    for pack in load_policy_packs():
        pack_id = str(pack.get("id", "")).strip()
        if not pack_id:
            continue
        versions.append(
            {
                "pack_type": "policy_pack",
                "pack_id": pack_id,
                "version": str(pack.get("version", "unknown")),
            }
        )
    return sorted(versions, key=lambda row: (row["pack_type"], row["pack_id"]))


def _collect_manifest_hashes() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "MANIFEST.sha256"
    if not manifest_path.exists():
        return {"status": "missing"}
    content = manifest_path.read_text(encoding="utf-8")
    entries = [line.strip() for line in content.splitlines() if line.strip()]
    return {
        "status": "ok",
        "manifest_file_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "entry_count": len(entries),
        "sample_entries": entries[:20],
    }
