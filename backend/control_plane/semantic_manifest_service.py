"""Semantic manifest lifecycle controls with review-gated publish and rollback."""

from __future__ import annotations

import json
from collections.abc import Mapping
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
from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest

ACTIVE_POLICY_TYPE = "semantic_manifest"
CHANGE_REQUEST_POLICY_TYPE = "semantic_manifest_change_request"


def request_semantic_manifest_change(
    session: Session,
    *,
    workspace_id: str,
    requester_actor_id: str,
    semantic_manifest: dict[str, object],
    storage_root: str,
) -> dict[str, object]:
    """Create review-gated semantic manifest change request."""
    _require_workspace(session, workspace_id=workspace_id)
    normalized_manifest = _validated_manifest(
        semantic_manifest, expected_workspace_id=workspace_id
    )
    manifest_checksum = semantic_manifest_checksum(normalized_manifest)
    current = get_effective_semantic_manifest(session, workspace_id=workspace_id)
    if current is not None and str(current.get("manifest_checksum")) == manifest_checksum:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "semantic_manifest_already_active"},
        )

    evidence_payload: dict[str, object] = {
        "workspace_id": workspace_id,
        "requested_manifest": normalized_manifest,
        "requested_manifest_checksum": manifest_checksum,
        "current_manifest": current,
    }
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="semantic_manifest_change",
        payload=evidence_payload,
    )
    proposal = create_proposal(
        session,
        workspace_id=workspace_id,
        proposal_type="semantic_manifest_change_proposal",
        evidence_bundle_uri=stored.evidence_bundle_uri,
        confidence=1.0,
    )
    review_task = create_review_task(
        session,
        workspace_id=workspace_id,
        subject_ref=str(proposal["proposal_id"]),
        priority="quality_critical",
        blocking=True,
    )
    change_request_id = new_ulid()
    change_request: dict[str, object] = {
        "change_request_id": change_request_id,
        "workspace_id": workspace_id,
        "manifest_checksum": manifest_checksum,
        "requester_actor_id": requester_actor_id,
        "proposal_id": str(proposal["proposal_id"]),
        "review_task_id": str(review_task["task_id"]),
        "semantic_manifest": normalized_manifest,
        "status": "staged",
    }
    session.add(
        GovernancePolicy(
            policy_id=change_request_id,
            workspace_id=workspace_id,
            policy_type=CHANGE_REQUEST_POLICY_TYPE,
            definition_ref=json.dumps(change_request, sort_keys=True),
            status="staged",
        )
    )
    session.flush()
    return change_request


def decide_semantic_manifest_change(
    session: Session,
    *,
    workspace_id: str,
    change_request_id: str,
    approver_actor_id: str,
    decision: str,
    reason: str,
) -> dict[str, object] | None:
    """Apply approval decision to staged semantic manifest change."""
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
        staged_row.status = str(staged["status"])
        staged_row.definition_ref = json.dumps(staged, sort_keys=True)
        session.flush()
        return staged

    requested_manifest_raw = staged.get("semantic_manifest", {})
    if not isinstance(requested_manifest_raw, dict):
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "invalid_semantic_manifest_request"},
        )
    normalized_manifest = _validated_manifest(
        requested_manifest_raw, expected_workspace_id=workspace_id
    )
    manifest_checksum = semantic_manifest_checksum(normalized_manifest)
    active_row = _get_active_semantic_manifest_row(session, workspace_id=workspace_id)
    active_state = _load_definition(active_row.definition_ref) if active_row is not None else {}
    next_version = _coerce_int(active_state.get("version"), default=0) + 1
    next_state: dict[str, object] = {
        "workspace_id": workspace_id,
        "manifest": normalized_manifest,
        "manifest_checksum": manifest_checksum,
        "version": next_version,
        "previous_manifest": active_state.get("manifest"),
        "previous_manifest_checksum": active_state.get("manifest_checksum"),
    }
    if active_row is None:
        active_row = GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type=ACTIVE_POLICY_TYPE,
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
        "effective_semantic_manifest": next_state,
    }


def rollback_semantic_manifest(session: Session, *, workspace_id: str) -> dict[str, object]:
    """Rollback semantic manifest to prior published state."""
    active_row = _get_active_semantic_manifest_row(session, workspace_id=workspace_id)
    if active_row is None:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "semantic_manifest_not_configured"},
        )
    active = _load_definition(active_row.definition_ref)
    previous_manifest_raw = active.get("previous_manifest")
    if not isinstance(previous_manifest_raw, dict):
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "semantic_manifest_rollback_unavailable"},
        )
    normalized_manifest = _validated_manifest(
        previous_manifest_raw, expected_workspace_id=workspace_id
    )
    next_version = _coerce_int(active.get("version"), default=0) + 1
    rollback_state = {
        "workspace_id": workspace_id,
        "manifest": normalized_manifest,
        "manifest_checksum": semantic_manifest_checksum(normalized_manifest),
        "version": next_version,
        "previous_manifest": active.get("manifest"),
        "previous_manifest_checksum": active.get("manifest_checksum"),
    }
    active_row.definition_ref = json.dumps(rollback_state, sort_keys=True)
    session.flush()
    return {"status": "rolled_back", "effective_semantic_manifest": rollback_state}


def get_effective_semantic_manifest(
    session: Session, *, workspace_id: str
) -> dict[str, object] | None:
    """Return active semantic manifest state for workspace."""
    active_row = _get_active_semantic_manifest_row(session, workspace_id=workspace_id)
    if active_row is None:
        return None
    state = _load_definition(active_row.definition_ref)
    manifest_raw = state.get("manifest")
    if not isinstance(manifest_raw, dict):
        return None
    normalized_manifest = _validated_manifest(manifest_raw, expected_workspace_id=workspace_id)
    checksum = str(state.get("manifest_checksum", "")).strip()
    if not checksum:
        checksum = semantic_manifest_checksum(normalized_manifest)
    return {
        "workspace_id": workspace_id,
        "manifest": normalized_manifest,
        "manifest_checksum": checksum,
        "version": _coerce_int(state.get("version"), default=1),
        "previous_manifest_checksum": str(state.get("previous_manifest_checksum", "")),
    }


def _get_active_semantic_manifest_row(
    session: Session, *, workspace_id: str
) -> GovernancePolicy | None:
    return (
        session.execute(
            select(GovernancePolicy).where(
                GovernancePolicy.workspace_id == workspace_id,
                GovernancePolicy.policy_type == ACTIVE_POLICY_TYPE,
                GovernancePolicy.status == "active",
            )
        )
        .scalars()
        .first()
    )


def _get_change_request_row(
    session: Session, *, workspace_id: str, change_request_id: str
) -> GovernancePolicy | None:
    row = session.get(GovernancePolicy, change_request_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    if row.policy_type != CHANGE_REQUEST_POLICY_TYPE:
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


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _validated_manifest(
    manifest: Mapping[str, object] | dict[str, object],
    *,
    expected_workspace_id: str,
) -> dict[str, object]:
    try:
        return validate_semantic_manifest(manifest, expected_workspace_id=expected_workspace_id)
    except ValueError as exc:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "invalid_semantic_manifest", "error": str(exc)},
        ) from exc


def _require_workspace(session: Session, *, workspace_id: str) -> None:
    if session.get(Workspace, workspace_id) is None:
        raise NotFoundError("Workspace not found.", details={"workspace_id": workspace_id})
