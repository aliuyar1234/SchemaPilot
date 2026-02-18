"""Policy-pack lifecycle controls with approval-gated apply and rollback."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.control_plane.review_repository import (
    create_proposal,
    create_review_task,
    decide_review_task,
)
from backend.shared_domain.errors import NotFoundError, PolicyDeniedError
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import GovernancePolicy, Workspace
from backend.shared_domain.policy_pack_tests import evaluate_policy_pack_invariants
from backend.shared_domain.policy_packs import load_policy_packs


def request_policy_pack_change(
    session: Session,
    *,
    workspace_id: str,
    requester_actor_id: str,
    requested_pack_id: str,
    storage_root: str,
) -> dict[str, object]:
    """Create approval-gated staged policy-pack change request."""
    _require_workspace(session, workspace_id=workspace_id)
    requested_pack = _load_policy_pack(requested_pack_id)
    current = get_effective_policy_pack(session, workspace_id=workspace_id)
    if current is not None and str(current.get("pack_id")) == requested_pack_id:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "policy_pack_already_active", "pack_id": requested_pack_id},
        )

    requested_checksum = _pack_checksum(requested_pack)
    evidence_payload: dict[str, object] = {
        "workspace_id": workspace_id,
        "requested_pack_id": requested_pack_id,
        "requested_pack_checksum": requested_checksum,
        "current_pack": current,
    }
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="policy_pack_change",
        payload=evidence_payload,
    )
    proposal = create_proposal(
        session,
        workspace_id=workspace_id,
        proposal_type="policy_pack_change_proposal",
        evidence_bundle_uri=stored.evidence_bundle_uri,
        confidence=1.0,
    )
    review_task = create_review_task(
        session,
        workspace_id=workspace_id,
        subject_ref=str(proposal["proposal_id"]),
        priority="security_critical",
        blocking=True,
    )
    change_request_id = new_ulid()
    change_request: dict[str, object] = {
        "change_request_id": change_request_id,
        "workspace_id": workspace_id,
        "requested_pack_id": requested_pack_id,
        "requested_pack_checksum": requested_checksum,
        "requester_actor_id": requester_actor_id,
        "proposal_id": str(proposal["proposal_id"]),
        "review_task_id": str(review_task["task_id"]),
        "status": "staged",
    }
    session.add(
        GovernancePolicy(
            policy_id=change_request_id,
            workspace_id=workspace_id,
            policy_type="policy_pack_change_request",
            definition_ref=json.dumps(change_request, sort_keys=True),
            status="staged",
        )
    )
    session.flush()
    return change_request


def decide_policy_pack_change(
    session: Session,
    *,
    workspace_id: str,
    change_request_id: str,
    approver_actor_id: str,
    decision: str,
    reason: str,
    canary_enabled: bool = False,
) -> dict[str, object] | None:
    """Approve/reject/defer staged policy-pack changes and apply when approved."""
    staged_row = _get_change_request_row(
        session,
        workspace_id=workspace_id,
        change_request_id=change_request_id,
    )
    if staged_row is None:
        return None
    staged = _load_definition(staged_row.definition_ref)
    review_task_id = str(staged.get("review_task_id", ""))
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject", "defer"}:
        normalized_decision = "defer"

    if review_task_id:
        decide_review_task(
            session,
            workspace_id=workspace_id,
            task_id=review_task_id,
            actor_id=approver_actor_id,
            decision=normalized_decision,
            reason=reason,
        )

    if normalized_decision != "approve":
        staged["status"] = "rejected" if normalized_decision == "reject" else "deferred"
        staged["approved_by"] = approver_actor_id
        staged["decision_reason"] = reason
        staged_row.status = staged["status"]
        staged_row.definition_ref = json.dumps(staged, sort_keys=True)
        session.flush()
        return staged

    active_row = _get_active_policy_pack_row(session, workspace_id=workspace_id)
    active = _load_definition(active_row.definition_ref) if active_row is not None else {}
    requested_pack_id = str(staged.get("requested_pack_id", "")).strip()
    requested_pack = _load_policy_pack(requested_pack_id)
    invariant_failures = evaluate_policy_pack_invariants(requested_pack)
    if invariant_failures:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={
                "reason": "policy_pack_test_failed",
                "pack_id": requested_pack_id,
                "failures": invariant_failures,
            },
        )
    if canary_enabled:
        canary_state = _upsert_policy_pack_canary(
            session,
            workspace_id=workspace_id,
            requested_pack_id=requested_pack_id,
            requested_pack_checksum=str(staged.get("requested_pack_checksum", "")),
            requested_by=str(staged.get("requester_actor_id", "")),
            approved_by=approver_actor_id,
            change_request_id=change_request_id,
        )
        staged["status"] = "canary_active"
        staged["approved_by"] = approver_actor_id
        staged["decision_reason"] = reason
        staged_row.status = "canary_active"
        staged_row.definition_ref = json.dumps(staged, sort_keys=True)
        session.flush()
        return {
            "change_request_id": change_request_id,
            "status": "canary_active",
            "canary": canary_state,
        }
    current_version = int(active.get("version", 0))
    next_version = current_version + 1
    next_state = {
        "workspace_id": workspace_id,
        "pack_id": requested_pack_id,
        "pack_checksum": str(staged.get("requested_pack_checksum", "")),
        "version": next_version,
        "previous_pack_id": str(active.get("pack_id", "")),
        "previous_pack_checksum": str(active.get("pack_checksum", "")),
    }
    if active_row is None:
        active_row = GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type="policy_pack",
            definition_ref=json.dumps(next_state, sort_keys=True),
            status="active",
        )
        session.add(active_row)
    else:
        active_row.definition_ref = json.dumps(next_state, sort_keys=True)
        active_row.status = "active"

    staged["status"] = "applied"
    staged["approved_by"] = approver_actor_id
    staged["decision_reason"] = reason
    staged_row.status = "applied"
    staged_row.definition_ref = json.dumps(staged, sort_keys=True)
    session.flush()
    return {
        "change_request_id": change_request_id,
        "status": "applied",
        "effective_policy_pack": next_state,
    }


def rollback_policy_pack(
    session: Session,
    *,
    workspace_id: str,
) -> dict[str, object]:
    """Rollback effective policy pack to previous version."""
    active_row = _get_active_policy_pack_row(session, workspace_id=workspace_id)
    if active_row is None:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "policy_pack_not_configured"},
        )
    active = _load_definition(active_row.definition_ref)
    previous_pack_id = str(active.get("previous_pack_id", "")).strip()
    previous_checksum = str(active.get("previous_pack_checksum", "")).strip()
    if not previous_pack_id or not previous_checksum:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "policy_pack_rollback_unavailable"},
        )
    next_version = int(active.get("version", 0)) + 1
    rollback_state = {
        "workspace_id": workspace_id,
        "pack_id": previous_pack_id,
        "pack_checksum": previous_checksum,
        "version": next_version,
        "previous_pack_id": str(active.get("pack_id", "")),
        "previous_pack_checksum": str(active.get("pack_checksum", "")),
    }
    active_row.definition_ref = json.dumps(rollback_state, sort_keys=True)
    session.flush()
    return {"status": "rolled_back", "effective_policy_pack": rollback_state}


def get_policy_pack_canary(
    session: Session, *, workspace_id: str
) -> dict[str, object] | None:
    """Return canary policy-pack state for a workspace."""
    row = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == "policy_pack_canary",
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    definition = _load_definition(row.definition_ref)
    return {
        "workspace_id": workspace_id,
        "pack_id": str(definition.get("pack_id", "")),
        "pack_checksum": str(definition.get("pack_checksum", "")),
        "requested_by": str(definition.get("requested_by", "")),
        "approved_by": str(definition.get("approved_by", "")),
        "change_request_id": str(definition.get("change_request_id", "")),
        "status": str(definition.get("status", "canary_active")),
    }


def promote_policy_pack_canary(
    session: Session,
    *,
    workspace_id: str,
    actor_id: str,
) -> dict[str, object]:
    """Promote active canary policy pack into effective policy pack."""
    canary = get_policy_pack_canary(session, workspace_id=workspace_id)
    if canary is None:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "policy_pack_canary_not_found"},
        )
    active = get_effective_policy_pack(session, workspace_id=workspace_id) or {}
    next_version = int(active.get("version", 0)) + 1
    next_state = {
        "workspace_id": workspace_id,
        "pack_id": canary["pack_id"],
        "pack_checksum": canary["pack_checksum"],
        "version": next_version,
        "previous_pack_id": str(active.get("pack_id", "")),
        "previous_pack_checksum": str(active.get("pack_checksum", "")),
    }
    active_row = _get_active_policy_pack_row(session, workspace_id=workspace_id)
    if active_row is None:
        active_row = GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type="policy_pack",
            definition_ref=json.dumps(next_state, sort_keys=True),
            status="active",
        )
        session.add(active_row)
    else:
        active_row.definition_ref = json.dumps(next_state, sort_keys=True)
        active_row.status = "active"
    row = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == "policy_pack_canary",
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )
    if row is not None:
        definition = _load_definition(row.definition_ref)
        definition["status"] = "promoted"
        definition["promoted_by"] = actor_id
        row.definition_ref = json.dumps(definition, sort_keys=True)
        row.status = "promoted"
    session.flush()
    return {
        "status": "promoted",
        "effective_policy_pack": next_state,
        "canary_change_request_id": canary["change_request_id"],
    }


def get_effective_policy_pack(
    session: Session, *, workspace_id: str
) -> dict[str, object] | None:
    """Return effective policy-pack state for a workspace."""
    active_row = _get_active_policy_pack_row(session, workspace_id=workspace_id)
    if active_row is None:
        return None
    definition = _load_definition(active_row.definition_ref)
    return {
        "workspace_id": workspace_id,
        "pack_id": str(definition.get("pack_id", "")),
        "pack_checksum": str(definition.get("pack_checksum", "")),
        "version": int(definition.get("version", 0)),
        "previous_pack_id": str(definition.get("previous_pack_id", "")),
        "previous_pack_checksum": str(definition.get("previous_pack_checksum", "")),
    }


def _load_policy_pack(pack_id: str) -> dict[str, object]:
    for pack in load_policy_packs():
        if str(pack.get("id", "")) == pack_id:
            return pack
    raise NotFoundError("Policy pack not found.", details={"pack_id": pack_id})


def _pack_checksum(pack: dict[str, object]) -> str:
    canonical = json.dumps(pack, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _upsert_policy_pack_canary(
    session: Session,
    *,
    workspace_id: str,
    requested_pack_id: str,
    requested_pack_checksum: str,
    requested_by: str,
    approved_by: str,
    change_request_id: str,
) -> dict[str, object]:
    payload = {
        "workspace_id": workspace_id,
        "pack_id": requested_pack_id,
        "pack_checksum": requested_pack_checksum,
        "requested_by": requested_by,
        "approved_by": approved_by,
        "change_request_id": change_request_id,
        "status": "canary_active",
    }
    existing = (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == "policy_pack_canary",
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        existing = GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type="policy_pack_canary",
            definition_ref=json.dumps(payload, sort_keys=True),
            status="active",
        )
        session.add(existing)
    else:
        existing.definition_ref = json.dumps(payload, sort_keys=True)
        existing.status = "active"
    session.flush()
    return payload


def _get_active_policy_pack_row(session: Session, *, workspace_id: str) -> GovernancePolicy | None:
    return (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == "policy_pack",
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )


def _get_change_request_row(
    session: Session,
    *,
    workspace_id: str,
    change_request_id: str,
) -> GovernancePolicy | None:
    row = session.get(GovernancePolicy, change_request_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    if row.policy_type != "policy_pack_change_request":
        return None
    return row


def _load_definition(definition_ref: str) -> dict[str, Any]:
    try:
        payload = json.loads(definition_ref)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _require_workspace(session: Session, *, workspace_id: str) -> None:
    if session.get(Workspace, workspace_id) is None:
        raise NotFoundError("Workspace not found.", details={"workspace_id": workspace_id})
