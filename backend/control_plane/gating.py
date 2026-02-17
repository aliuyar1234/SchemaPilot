"""Build gating rules for fail-closed gold publication."""

from __future__ import annotations


def evaluate_gold_publish_gate(
    *,
    contracts_passed: bool,
    unresolved_blocking_tasks: int,
) -> dict[str, object]:
    """Evaluate publication gate for gold build pointer updates."""
    if not contracts_passed:
        return {"allowed": False, "reason": "contract_failure"}
    if unresolved_blocking_tasks > 0:
        return {"allowed": False, "reason": "blocking_review_tasks"}
    return {"allowed": True, "reason": "all_gates_passed"}
