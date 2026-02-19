#!/usr/bin/env python3
"""Export governance-only auditor bundle (no raw data payloads)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path

from sqlalchemy import select

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import GovernancePolicy, RunRecord


def export_auditor_bundle(
    *,
    database_url: str,
    output_path: Path,
    packs_registry_path: Path,
    signing_key: str | None = None,
) -> dict[str, object]:
    """Write deterministic, redaction-safe governance export for auditors."""
    engine = get_engine(database_url)
    GovernancePolicy.metadata.create_all(bind=engine)
    AuditEvent.metadata.create_all(bind=engine)
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        policies = (
            session.execute(
                select(GovernancePolicy).order_by(
                    GovernancePolicy.workspace_id,
                    GovernancePolicy.policy_type,
                    GovernancePolicy.policy_id,
                )
            )
            .scalars()
            .all()
        )
        events = (
            session.execute(select(AuditEvent).order_by(AuditEvent.audit_event_id))
            .scalars()
            .all()
        )
        decisions = (
            session.execute(select(AccessDecision).order_by(AccessDecision.decision_id))
            .scalars()
            .all()
        )
        runs = (
            session.execute(select(RunRecord).order_by(RunRecord.workspace_id, RunRecord.run_id))
            .scalars()
            .all()
        )

    bundle = {
        "schema_version": "v1",
        "policy_decisions": [
            {
                "workspace_id": row.workspace_id,
                "policy_id": row.policy_id,
                "policy_type": row.policy_type,
                "status": row.status,
                "definition_checksum": _checksum(str(row.definition_ref)),
            }
            for row in policies
        ],
        "audit_summary": {
            "event_count": len(events),
            "decision_count": len(decisions),
            "event_types": sorted({str(event.event_type) for event in events}),
            "decision_results": sorted({str(decision.result) for decision in decisions}),
        },
        "attestations": [
            {
                "workspace_id": event.workspace_id,
                "event_type": event.event_type,
                "audit_event_id": event.audit_event_id,
                "correlation_id": event.correlation_id,
            }
            for event in events
            if "attestation" in str(event.event_type)
            or "promotion" in str(event.event_type)
            or "policy_pack" in str(event.event_type)
        ],
        "lineage_refs": [
            {
                "workspace_id": run.workspace_id,
                "run_id": run.run_id,
                "run_type": run.run_type,
                "output_ref_checksum": _checksum(json.dumps(run.output_refs_json, sort_keys=True)),
            }
            for run in runs
        ],
        "pack_registry": _pack_registry_summary(packs_registry_path),
    }
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    result: dict[str, object] = {
        "bundle_checksum": _checksum(canonical),
        "bundle": bundle,
    }
    if signing_key:
        signature = hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256)
        result["signature"] = {
            "algorithm": "hmac-sha256",
            "value": signature.hexdigest(),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "pass",
        "output_path": output_path.as_posix(),
        "bundle_checksum": result["bundle_checksum"],
    }


def _checksum(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pack_registry_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "missing", "path": path.as_posix(), "counts": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"status": "invalid", "path": path.as_posix(), "counts": {}}
    counts: dict[str, int] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            counts[str(key)] = len(value)
    return {
        "status": "ok",
        "path": path.as_posix(),
        "counts": counts,
        "checksum": _checksum(json.dumps(payload, sort_keys=True)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db"),
    )
    parser.add_argument("--output", default="runtime/auditor/export.json")
    parser.add_argument("--pack-registry", default="packs/registry.json")
    parser.add_argument(
        "--signing-key",
        default=os.getenv("SCHEMAPILOT_AUDITOR_EXPORT_SIGNING_KEY"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_auditor_bundle(
        database_url=str(args.database_url),
        output_path=Path(args.output),
        packs_registry_path=Path(args.pack_registry),
        signing_key=str(args.signing_key) if args.signing_key else None,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
