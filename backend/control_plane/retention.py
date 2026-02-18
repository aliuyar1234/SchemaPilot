"""Retention policy and purge orchestration for control-plane workflows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.errors import NotFoundError, PolicyDeniedError
from backend.shared_domain.evidence_store import store_evidence_bundle
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import (
    GovernancePurgeRun,
    GovernanceRetentionPolicy,
    Workspace,
)
from backend.shared_domain.purge import purge_workspace_artifacts


def configure_retention_policy(
    session: Session,
    *,
    workspace_id: str,
    actor_id: str,
    retention_days: int,
    enabled: bool,
    purge_enabled: bool,
    legal_hold_active: bool,
) -> dict[str, object]:
    """Create/update workspace retention policy with fail-closed validation."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found.", details={"workspace_id": workspace_id})
    if enabled and retention_days <= 0:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "invalid_retention_days", "retention_days": retention_days},
        )

    policy = _get_retention_policy_row(session, workspace_id=workspace_id)
    if policy is None:
        policy = GovernanceRetentionPolicy(
            retention_policy_id=new_ulid(),
            workspace_id=workspace_id,
            retention_days=retention_days,
            enabled=enabled,
            purge_enabled=purge_enabled,
            legal_hold_active=legal_hold_active,
            created_by=actor_id,
            status="active",
        )
        session.add(policy)
    else:
        policy.retention_days = retention_days
        policy.enabled = enabled
        policy.purge_enabled = purge_enabled
        policy.legal_hold_active = legal_hold_active
        policy.created_by = actor_id
        policy.status = "active"
    session.flush()
    return _serialize_retention_policy(policy)


def get_retention_policy(session: Session, *, workspace_id: str) -> dict[str, object] | None:
    """Return active retention policy for workspace."""
    policy = _get_retention_policy_row(session, workspace_id=workspace_id)
    if policy is None:
        return None
    return _serialize_retention_policy(policy)


def execute_retention_purge(
    session: Session,
    *,
    workspace_id: str,
    actor_id: str,
    storage_root: str,
    purge_root: str | None,
    dry_run: bool,
) -> dict[str, object]:
    """Run retention purge using explicit policy and immutable evidence output."""
    policy = _get_retention_policy_row(session, workspace_id=workspace_id)
    if policy is None or not policy.enabled:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "retention_disabled"},
        )
    if not policy.purge_enabled:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "purge_not_enabled"},
        )
    if policy.legal_hold_active:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "legal_hold_active"},
        )
    if purge_root is None or not purge_root.strip():
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "missing_purge_path_config"},
        )

    try:
        execution = purge_workspace_artifacts(
            workspace_id=workspace_id,
            purge_root=purge_root,
            retention_days=policy.retention_days,
            dry_run=dry_run,
        )
    except ValueError as exc:
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": str(exc)},
        ) from exc

    evidence_payload = {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "retention_policy_id": policy.retention_policy_id,
        "retention_days": policy.retention_days,
        "dry_run": dry_run,
        "scanned_count": execution.scanned_count,
        "deleted_count": execution.deleted_count,
        "deleted_paths": execution.deleted_paths,
        "cutoff_epoch": execution.cutoff_epoch,
    }
    stored = store_evidence_bundle(
        workspace_id=workspace_id,
        storage_root=storage_root,
        bundle_type="retention_purge",
        payload=evidence_payload,
    )
    run = GovernancePurgeRun(
        purge_run_id=new_ulid(),
        workspace_id=workspace_id,
        retention_policy_id=policy.retention_policy_id,
        dry_run=dry_run,
        status="succeeded",
        deleted_count=execution.deleted_count,
        deleted_paths_json=execution.deleted_paths,
        evidence_bundle_uri=stored.evidence_bundle_uri,
    )
    session.add(run)
    session.flush()
    return {
        "purge_run_id": run.purge_run_id,
        "workspace_id": workspace_id,
        "status": run.status,
        "dry_run": dry_run,
        "deleted_count": execution.deleted_count,
        "deleted_paths": execution.deleted_paths,
        "evidence_bundle_uri": stored.evidence_bundle_uri,
        "retention_policy_id": policy.retention_policy_id,
    }


def _get_retention_policy_row(
    session: Session, *, workspace_id: str
) -> GovernanceRetentionPolicy | None:
    return (
        session.execute(
            select(GovernanceRetentionPolicy)
            .where(GovernanceRetentionPolicy.workspace_id == workspace_id)
            .order_by(GovernanceRetentionPolicy.retention_policy_id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _serialize_retention_policy(policy: GovernanceRetentionPolicy) -> dict[str, object]:
    return {
        "retention_policy_id": policy.retention_policy_id,
        "workspace_id": policy.workspace_id,
        "retention_days": policy.retention_days,
        "enabled": policy.enabled,
        "purge_enabled": policy.purge_enabled,
        "legal_hold_active": policy.legal_hold_active,
        "created_by": policy.created_by,
        "status": policy.status,
    }
