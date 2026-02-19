from __future__ import annotations

from backend.workers.db_builder.materialize_manager import (
    apply_materialization_proposal,
    propose_materializations,
    rollback_materializations,
)


def test_materialization_proposal_apply_and_rollback() -> None:
    proposal = propose_materializations(
        workspace_id="w1",
        target_db_id="tdb1",
        target_build_id="b1",
        semantic_manifest={
            "metrics": [{"metric_id": "ticket_count", "expression": "count(*)"}],
        },
    )
    assert proposal.requires_approval is True
    try:
        apply_materialization_proposal(proposal, approved=False)
    except ValueError as exc:
        assert "materialization_approval_required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")

    applied = apply_materialization_proposal(proposal, approved=True)
    rollback = rollback_materializations(applied, expected_rollback_token=applied.rollback_token)
    assert rollback["status"] == "rolled_back"
    assert rollback["dropped_views"]
