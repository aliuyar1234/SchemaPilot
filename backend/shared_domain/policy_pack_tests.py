"""Policy pack invariant checks used before apply."""

from __future__ import annotations

from typing import Any


def evaluate_policy_pack_invariants(pack: dict[str, Any]) -> list[str]:
    """Return invariant failures for a policy pack payload."""
    failures: list[str] = []
    pack_id = str(pack.get("id", "")).strip()
    if not pack_id:
        failures.append("pack_id_missing")
    template_actor = pack.get("template_actor", {})
    if not isinstance(template_actor, dict):
        failures.append("template_actor_missing")
        return failures
    actor_type = str(template_actor.get("actor_type", "")).strip().lower()
    if actor_type not in {"human", "ai"}:
        failures.append("template_actor_type_invalid")
    roles_raw = template_actor.get("roles", [])
    if not isinstance(roles_raw, list) or not roles_raw:
        failures.append("template_roles_missing")
    else:
        roles = {str(role) for role in roles_raw}
        if actor_type == "ai" and "ai_agent" not in roles:
            failures.append("template_ai_role_missing")
    attributes = template_actor.get("attributes", {})
    if not isinstance(attributes, dict):
        failures.append("template_attributes_invalid")
    return failures
