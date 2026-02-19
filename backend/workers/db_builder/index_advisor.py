"""Approval-gated index advisor with deterministic rollback metadata."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from backend.workers.db_builder.index_planner import build_index_constraint_plan
from backend.workers.db_builder.materialize_manager import (
    MaterializationProposal,
    propose_materializations,
)


@dataclass(frozen=True)
class IndexAdvisorProposal:
    """Combined index/materialization advisor payload."""

    proposal_id: str
    plan_checksum: str
    statements: list[str]
    evidence_refs: list[str]
    requires_approval: bool
    materialization: MaterializationProposal


@dataclass(frozen=True)
class AppliedIndexAdvisorState:
    """Applied advisor state for deterministic rollback."""

    proposal_id: str
    applied_statements: list[str]
    rollback_token: str


def propose_index_materializations(
    *,
    workspace_id: str,
    target_db_id: str,
    db_type: str,
    schema: str | None,
    target_build_id: str,
    semantic_manifest: dict[str, object],
) -> IndexAdvisorProposal:
    """Build index/materialization proposal payload."""
    index_plan = build_index_constraint_plan(
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        db_type=db_type,
        schema=schema,
        target_build_id=target_build_id,
        semantic_manifest=semantic_manifest,
        include_constraints=True,
    )
    materialization = propose_materializations(
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        target_build_id=target_build_id,
        semantic_manifest=semantic_manifest,
    )
    statements = list(index_plan.statements)
    evidence_refs = [
        f"evidence://target_db/index_advisor/{workspace_id}/{target_db_id}/{target_build_id}",
        *materialization.evidence_refs,
    ]
    checksum = _checksum(
        {
            "index_plan_checksum": index_plan.plan_checksum,
            "materialization_plan_checksum": materialization.plan_checksum,
            "statements": statements,
        }
    )
    proposal_id = f"index-advisor-{target_build_id}"
    return IndexAdvisorProposal(
        proposal_id=proposal_id,
        plan_checksum=checksum,
        statements=statements,
        evidence_refs=evidence_refs,
        requires_approval=bool(statements or materialization.statements),
        materialization=materialization,
    )


def apply_index_advisor_proposal(
    proposal: IndexAdvisorProposal,
    *,
    approved: bool,
) -> AppliedIndexAdvisorState:
    """Apply advisor proposal only when approval exists."""
    if proposal.requires_approval and not approved:
        raise ValueError("index_advisor_approval_required")
    rollback_token = _checksum(
        {
            "proposal_id": proposal.proposal_id,
            "plan_checksum": proposal.plan_checksum,
            "statements": proposal.statements,
        }
    )
    return AppliedIndexAdvisorState(
        proposal_id=proposal.proposal_id,
        applied_statements=list(proposal.statements),
        rollback_token=rollback_token,
    )


def rollback_index_advisor(
    state: AppliedIndexAdvisorState,
    *,
    expected_rollback_token: str,
) -> dict[str, object]:
    """Generate deterministic rollback statements for applied indexes."""
    if state.rollback_token != expected_rollback_token:
        raise ValueError("index_advisor_rollback_token_mismatch")
    rollback_statements = sorted(
        _index_drop_statement(statement) for statement in state.applied_statements
    )
    return {
        "status": "rolled_back",
        "proposal_id": state.proposal_id,
        "rollback_statements": rollback_statements,
    }


def _index_drop_statement(statement: str) -> str:
    normalized = statement.strip().rstrip(";")
    if "CREATE INDEX IF NOT EXISTS" not in normalized:
        return f"-- noop rollback: {normalized}"
    parts = normalized.split()
    if len(parts) < 6:
        return f"-- noop rollback: {normalized}"
    index_name = parts[4]
    return f"DROP INDEX IF EXISTS {index_name};"


def _checksum(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
