"""Break-glass CLI payload helpers."""

from __future__ import annotations


def build_breakglass_request_payload(*, actor_id: str, ttl_seconds: int) -> dict[str, object]:
    """Build deterministic request payload for break-glass request creation."""

    return {
        "actor_id": actor_id.strip(),
        "ttl_seconds": max(int(ttl_seconds), 1),
    }


def build_breakglass_decision_payload(
    *, decision: str, decision_reason: str
) -> dict[str, object]:
    """Build deterministic payload for break-glass decision endpoint."""

    return {
        "decision": decision.strip().lower() or "approve",
        "decision_reason": decision_reason.strip(),
    }
