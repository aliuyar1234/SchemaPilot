"""Deletion workflow with legal hold blocking and evidence report output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.errors import PolicyDeniedError
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    GovernanceDeletionApproval,
    GovernanceDeletionRequest,
    GovernanceRetentionPolicy,
)


@dataclass(frozen=True)
class DeletionRequest:
    """Deletion workflow request."""

    workspace_id: str
    subject_selector: dict[str, object]
    legal_hold_active: bool
    approved: bool
    affected_snapshots: list[str]
    affected_indexes: list[str]
    backup_reference: str | None = None


def execute_deletion_workflow(request: DeletionRequest, output_root: str) -> dict[str, object]:
    """Execute deletion workflow in fail-closed mode."""
    impact_preview = {
        "subject_selector": request.subject_selector,
        "affected_snapshots": sorted(request.affected_snapshots),
        "affected_indexes": sorted(request.affected_indexes),
    }
    if request.legal_hold_active:
        return {
            "status": "blocked",
            "reason": "legal_hold_active",
            "evidence_report_path": None,
            "impact_preview": impact_preview,
        }
    if not request.approved:
        return {
            "status": "blocked",
            "reason": "missing_approval",
            "evidence_report_path": None,
            "impact_preview": impact_preview,
        }
    evidence = {
        "deletion_id": new_ulid(),
        "workspace_id": request.workspace_id,
        "subject_selector": request.subject_selector,
        "impact_preview": impact_preview,
        "approval": {"approved": True, "mode": "explicit_workflow"},
        "execution": {
            "status": "executed_stub",
            "snapshots_updated": sorted(request.affected_snapshots),
            "indexes_updated": sorted(request.affected_indexes),
            "records_deleted_estimate": len(request.affected_snapshots)
            + len(request.affected_indexes),
            "backup_reference": request.backup_reference,
        },
    }
    out_dir = Path(output_root) / "deletions" / request.workspace_id
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{evidence['deletion_id']}.json"
    report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "executed",
        "reason": "approved",
        "evidence_report_path": report_path.as_posix(),
    }


def submit_deletion_request(
    session: Session,
    *,
    workspace_id: str,
    requester_actor_id: str,
    subject_selector: dict[str, object],
    affected_snapshots: list[str],
    affected_indexes: list[str],
) -> dict[str, object]:
    """Create a deletion request with server-side legal hold state."""
    legal_hold_active = _legal_hold_active(session, workspace_id=workspace_id)
    row = GovernanceDeletionRequest(
        deletion_request_id=new_ulid(),
        workspace_id=workspace_id,
        requester_actor_id=requester_actor_id,
        status="requested",
        subject_selector_json=subject_selector,
        affected_snapshots_json=sorted(affected_snapshots),
        affected_indexes_json=sorted(affected_indexes),
        legal_hold_active=legal_hold_active,
        approval_reason=None,
        evidence_bundle_uri=None,
    )
    session.add(row)
    session.flush()
    return _serialize_deletion_request(row)


def approve_deletion_request(
    session: Session,
    *,
    workspace_id: str,
    deletion_request_id: str,
    approver_actor_id: str,
    decision: str,
    reason: str,
) -> dict[str, object] | None:
    """Apply deletion approval with separation-of-duties enforcement."""
    row = session.get(GovernanceDeletionRequest, deletion_request_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    normalized = decision.strip().lower()
    if normalized not in {"approve", "reject", "defer"}:
        normalized = "defer"
    if normalized == "approve" and row.requester_actor_id == approver_actor_id:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={
                "reason": "requester_cannot_self_approve",
                "deletion_request_id": deletion_request_id,
            },
        )
    if normalized == "approve" and _legal_hold_active(session, workspace_id=workspace_id):
        row.legal_hold_active = True
        row.status = "blocked"
        row.approval_reason = "legal_hold_active"
    elif normalized == "approve":
        row.status = "approved"
        row.approval_reason = reason
    elif normalized == "reject":
        row.status = "rejected"
        row.approval_reason = reason
    else:
        row.status = "deferred"
        row.approval_reason = reason
    approval = GovernanceDeletionApproval(
        deletion_approval_id=new_ulid(),
        deletion_request_id=row.deletion_request_id,
        workspace_id=row.workspace_id,
        approver_actor_id=approver_actor_id,
        decision=normalized,
        decision_reason=reason,
    )
    session.add(approval)
    session.flush()
    payload = _serialize_deletion_request(row)
    payload["approval"] = {
        "deletion_approval_id": approval.deletion_approval_id,
        "decision": approval.decision,
        "decision_reason": approval.decision_reason,
        "approver_actor_id": approval.approver_actor_id,
    }
    return payload


def execute_deletion_request(
    session: Session,
    *,
    workspace_id: str,
    deletion_request_id: str,
    output_root: str,
    storage_root: str,
    backup_reference: str | None,
) -> dict[str, object] | None:
    """Execute approved deletion request with server-side legal hold enforcement."""
    row = session.get(GovernanceDeletionRequest, deletion_request_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    legal_hold_active = _legal_hold_active(session, workspace_id=workspace_id)
    row.legal_hold_active = legal_hold_active
    if legal_hold_active:
        row.status = "blocked"
        row.approval_reason = "legal_hold_active"
        session.flush()
        return {
            "deletion_request_id": row.deletion_request_id,
            "workspace_id": row.workspace_id,
            "status": "blocked",
            "reason": "legal_hold_active",
        }
    if row.status != "approved":
        raise PolicyDeniedError(
            "Access denied by policy",
            details={
                "reason": "deletion_not_approved",
                "deletion_request_id": deletion_request_id,
                "status": row.status,
            },
        )

    workflow_result = execute_deletion_workflow(
        DeletionRequest(
            workspace_id=workspace_id,
            subject_selector=row.subject_selector_json,
            legal_hold_active=False,
            approved=True,
            affected_snapshots=list(row.affected_snapshots_json),
            affected_indexes=list(row.affected_indexes_json),
            backup_reference=backup_reference,
        ),
        output_root=output_root,
    )
    if workflow_result.get("status") != "executed":
        row.status = "blocked"
        row.approval_reason = str(workflow_result.get("reason", "execution_blocked"))
        session.flush()
        return {
            "deletion_request_id": row.deletion_request_id,
            "workspace_id": row.workspace_id,
            "status": "blocked",
            "reason": row.approval_reason,
        }

    report_path = str(workflow_result.get("evidence_report_path", ""))
    report_payload: dict[str, object] = {}
    if report_path:
        report_json = json.loads(Path(report_path).read_text(encoding="utf-8"))
        report_payload = report_json if isinstance(report_json, dict) else {}
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="deletion_execution",
        payload={
            "deletion_request_id": row.deletion_request_id,
            "workflow_result": workflow_result,
            "report": report_payload,
        },
    )
    row.status = "executed"
    row.evidence_bundle_uri = stored.evidence_bundle_uri
    session.flush()
    return {
        "deletion_request_id": row.deletion_request_id,
        "workspace_id": row.workspace_id,
        "status": "executed",
        "reason": "approved",
        "evidence_report_path": report_path,
        "evidence_bundle_uri": stored.evidence_bundle_uri,
    }


def get_deletion_request(
    session: Session, *, workspace_id: str, deletion_request_id: str
) -> dict[str, object] | None:
    """Return one deletion request."""
    row = session.get(GovernanceDeletionRequest, deletion_request_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    return _serialize_deletion_request(row)


def _legal_hold_active(session: Session, *, workspace_id: str) -> bool:
    row = (
        session.execute(
            select(GovernanceRetentionPolicy)
            .where(GovernanceRetentionPolicy.workspace_id == workspace_id)
            .order_by(GovernanceRetentionPolicy.retention_policy_id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        return False
    return bool(row.legal_hold_active)


def _serialize_deletion_request(row: GovernanceDeletionRequest) -> dict[str, object]:
    return {
        "deletion_request_id": row.deletion_request_id,
        "workspace_id": row.workspace_id,
        "requester_actor_id": row.requester_actor_id,
        "status": row.status,
        "subject_selector": row.subject_selector_json,
        "affected_snapshots": list(row.affected_snapshots_json),
        "affected_indexes": list(row.affected_indexes_json),
        "legal_hold_active": row.legal_hold_active,
        "approval_reason": row.approval_reason,
        "evidence_bundle_uri": row.evidence_bundle_uri,
    }
