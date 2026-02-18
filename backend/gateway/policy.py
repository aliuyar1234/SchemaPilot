"""Gateway policy evaluation baseline with deny-by-default semantics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessDecision:
    """Policy decision returned by gateway."""

    result: str
    reason: str
    applied_filters: list[str]
    applied_masks: list[str]


def evaluate_access(actor: dict[str, object], *, allow_ai: bool = False) -> AccessDecision:
    """Evaluate actor access using conservative default policy."""
    actor_type = str(actor.get("actor_type", "")).lower()
    if actor_type == "ai":
        if allow_ai:
            return AccessDecision(
                result="allow",
                reason="ai_allowlisted",
                applied_filters=[],
                applied_masks=[],
            )
        return AccessDecision(
            result="deny",
            reason="ai_tool_deny_by_default",
            applied_filters=[],
            applied_masks=[],
        )

    roles_raw = actor.get("roles", [])
    roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
    if not roles:
        return AccessDecision(
            result="deny", reason="missing_roles", applied_filters=[], applied_masks=[]
        )

    if "analyst" in roles or "data_steward" in roles or "platform_admin" in roles:
        return AccessDecision(
            result="allow",
            reason="explicit_role_allow",
            applied_filters=[],
            applied_masks=[],
        )

    return AccessDecision(
        result="deny", reason="role_not_allowed", applied_filters=[], applied_masks=[]
    )
