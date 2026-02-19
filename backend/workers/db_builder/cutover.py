"""Optional multi-target shadow cutover planning and rollback helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowCutoverPlan:
    """Deterministic shadow cutover plan."""

    workspace_id: str
    from_target_db_id: str | None
    to_target_db_id: str
    requires_approval: bool
    plan_checksum: str


def build_shadow_cutover_plan(
    *,
    workspace_id: str,
    from_target_db_id: str | None,
    to_target_db_id: str,
) -> ShadowCutoverPlan:
    """Build a shadow cutover plan with deterministic checksum."""
    payload = {
        "workspace_id": workspace_id,
        "from_target_db_id": str(from_target_db_id or ""),
        "to_target_db_id": to_target_db_id,
    }
    checksum = "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ShadowCutoverPlan(
        workspace_id=workspace_id,
        from_target_db_id=from_target_db_id,
        to_target_db_id=to_target_db_id,
        requires_approval=True,
        plan_checksum=checksum,
    )


def apply_shadow_cutover(
    *,
    plan: ShadowCutoverPlan,
    approved: bool,
    current_active_target_db_id: str | None,
) -> dict[str, object]:
    """Apply a cutover plan atomically when approval exists."""
    if plan.requires_approval and not approved:
        raise ValueError("shadow_cutover_approval_required")
    if plan.from_target_db_id and current_active_target_db_id and (
        plan.from_target_db_id != current_active_target_db_id
    ):
        raise ValueError("shadow_cutover_source_mismatch")
    return {
        "status": "cutover_applied",
        "workspace_id": plan.workspace_id,
        "from_target_db_id": current_active_target_db_id,
        "to_target_db_id": plan.to_target_db_id,
        "rollback_target_db_id": current_active_target_db_id,
        "plan_checksum": plan.plan_checksum,
    }


def rollback_shadow_cutover(
    *,
    workspace_id: str,
    rollback_target_db_id: str | None,
) -> dict[str, object]:
    """Build rollback payload for a previous cutover."""
    if not rollback_target_db_id:
        raise ValueError("shadow_cutover_rollback_target_required")
    return {
        "status": "rollback_ready",
        "workspace_id": workspace_id,
        "to_target_db_id": rollback_target_db_id,
    }
