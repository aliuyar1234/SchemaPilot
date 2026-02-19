"""Proposal-only materialization advisor with explicit apply/rollback flow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class MaterializationProposal:
    """Deterministic materialization proposal payload."""

    proposal_id: str
    target_build_id: str
    statements: list[str]
    evidence_refs: list[str]
    plan_checksum: str
    requires_approval: bool


@dataclass(frozen=True)
class AppliedMaterializationState:
    """Applied materialization state with rollback token."""

    proposal_id: str
    applied_statements: list[str]
    rollback_token: str


def propose_materializations(
    *,
    workspace_id: str,
    target_db_id: str,
    target_build_id: str,
    semantic_manifest: dict[str, object],
) -> MaterializationProposal:
    """Propose conservative metric materializations from semantic manifest metadata."""
    metrics_raw = semantic_manifest.get("metrics", [])
    metrics = metrics_raw if isinstance(metrics_raw, list) else []
    statements: list[str] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_id = str(metric.get("metric_id", "")).strip().lower()
        expression = str(metric.get("expression", "")).strip()
        if not metric_id or not expression:
            continue
        view_name = f"mv_{metric_id}"
        statements.append(
            "CREATE MATERIALIZED VIEW IF NOT EXISTS "
            f"{view_name} AS SELECT {expression} AS {metric_id};"
        )
    evidence_refs = [
        f"evidence://target_db/materialization/{workspace_id}/{target_db_id}/{target_build_id}"
    ]
    checksum = _checksum(
        {
            "workspace_id": workspace_id,
            "target_db_id": target_db_id,
            "target_build_id": target_build_id,
            "statements": statements,
        }
    )
    proposal_id = f"materialize-{target_build_id}"
    return MaterializationProposal(
        proposal_id=proposal_id,
        target_build_id=target_build_id,
        statements=statements,
        evidence_refs=evidence_refs,
        plan_checksum=checksum,
        requires_approval=bool(statements),
    )


def apply_materialization_proposal(
    proposal: MaterializationProposal,
    *,
    approved: bool,
) -> AppliedMaterializationState:
    """Apply one proposal only when explicitly approved."""
    if proposal.requires_approval and not approved:
        raise ValueError("materialization_approval_required")
    rollback_token = _checksum(
        {
            "proposal_id": proposal.proposal_id,
            "plan_checksum": proposal.plan_checksum,
            "statements": proposal.statements,
        }
    )
    return AppliedMaterializationState(
        proposal_id=proposal.proposal_id,
        applied_statements=list(proposal.statements),
        rollback_token=rollback_token,
    )


def rollback_materializations(
    state: AppliedMaterializationState,
    *,
    expected_rollback_token: str,
) -> dict[str, object]:
    """Build deterministic rollback payload for previously applied materializations."""
    if state.rollback_token != expected_rollback_token:
        raise ValueError("materialization_rollback_token_mismatch")
    return {
        "status": "rolled_back",
        "proposal_id": state.proposal_id,
        "dropped_views": sorted(_extract_view_names(state.applied_statements)),
    }


def _extract_view_names(statements: list[str]) -> list[str]:
    names: list[str] = []
    for statement in statements:
        parts = statement.strip().split()
        if len(parts) < 6:
            continue
        if parts[0].upper() != "CREATE" or parts[1].upper() != "MATERIALIZED":
            continue
        names.append(parts[5])
    return names


def _checksum(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
