from __future__ import annotations

from backend.workers.db_builder.index_advisor import (
    apply_index_advisor_proposal,
    propose_index_materializations,
    rollback_index_advisor,
)


def _semantic_manifest() -> dict[str, object]:
    return {
        "entities": [
            {
                "entity_id": "invoice",
                "primary_key": "invoice_id",
                "attributes": ["invoice_id", "customer_id", "status"],
            }
        ],
        "metrics": [
            {
                "metric_id": "invoice_count",
                "expression": "count(*)",
            }
        ],
    }


def test_index_advisor_proposal_contains_evidence_and_requires_approval() -> None:
    proposal = propose_index_materializations(
        workspace_id="w1",
        target_db_id="tdb1",
        db_type="postgres",
        schema="public",
        target_build_id="b1",
        semantic_manifest=_semantic_manifest(),
    )
    assert proposal.plan_checksum.startswith("sha256:")
    assert proposal.requires_approval is True
    assert proposal.evidence_refs
    assert proposal.materialization.plan_checksum.startswith("sha256:")


def test_index_advisor_apply_requires_approval_and_supports_rollback() -> None:
    proposal = propose_index_materializations(
        workspace_id="w1",
        target_db_id="tdb1",
        db_type="postgres",
        schema="public",
        target_build_id="b1",
        semantic_manifest=_semantic_manifest(),
    )
    try:
        apply_index_advisor_proposal(proposal, approved=False)
    except ValueError as exc:
        assert "index_advisor_approval_required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")

    applied = apply_index_advisor_proposal(proposal, approved=True)
    rollback = rollback_index_advisor(
        applied,
        expected_rollback_token=applied.rollback_token,
    )
    assert rollback["status"] == "rolled_back"
