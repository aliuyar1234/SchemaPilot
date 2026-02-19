"""Role-aware gateway query budget resolution."""

from __future__ import annotations

import json
import os
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.shared_domain.metadata_models import GovernancePolicy

QUERY_BUDGET_POLICY_TYPE = "query_budget"


def resolve_query_budget(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
    actor_roles: list[str],
    default_budget_bytes: int,
) -> dict[str, object]:
    """Resolve effective query budget in bytes for one actor."""
    policy = _load_query_budget_policy(session_factory=session_factory, workspace_id=workspace_id)
    if policy is None:
        policy = _load_query_budget_policy_from_env()
    if policy is None:
        return {
            "query_budget_bytes": max(default_budget_bytes, 1),
            "source": "default",
            "matched_role": None,
        }
    per_role_raw = policy.get("per_role_bytes", {})
    per_role = per_role_raw if isinstance(per_role_raw, dict) else {}
    for role in actor_roles:
        value = per_role.get(role)
        if value is None:
            continue
        bytes_value = _as_positive_int(value, fallback=default_budget_bytes)
        return {
            "query_budget_bytes": bytes_value,
            "source": "policy_per_role",
            "matched_role": role,
        }
    fallback_raw = policy.get("default_bytes", default_budget_bytes)
    fallback = _as_positive_int(fallback_raw, fallback=default_budget_bytes)
    return {
        "query_budget_bytes": fallback,
        "source": "policy_default",
        "matched_role": None,
    }


def _load_query_budget_policy(
    *, session_factory: Callable[[], Session], workspace_id: str
) -> dict[str, object] | None:
    session = session_factory()
    try:
        row = (
            session.execute(
                select(GovernancePolicy).where(
                    GovernancePolicy.workspace_id == workspace_id,
                    GovernancePolicy.policy_type == QUERY_BUDGET_POLICY_TYPE,
                    GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
    finally:
        session.close()
    if row is None:
        return None
    try:
        payload = json.loads(row.definition_ref)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return {str(key): value for key, value in payload.items()}


def _load_query_budget_policy_from_env() -> dict[str, object] | None:
    raw = os.getenv("SCHEMAPILOT_QUERY_BUDGETS_BY_ROLE", "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    default_bytes = _as_positive_int(payload.get("default_bytes"), fallback=0)
    per_role_raw = payload.get("per_role_bytes", {})
    per_role = per_role_raw if isinstance(per_role_raw, dict) else {}
    normalized_per_role = {
        str(role): _as_positive_int(value, fallback=0)
        for role, value in per_role.items()
        if _as_positive_int(value, fallback=0) > 0
    }
    return {
        "default_bytes": default_bytes,
        "per_role_bytes": normalized_per_role,
    }


def _as_positive_int(value: object, *, fallback: int) -> int:
    parsed: int
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value)
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            parsed = fallback
    else:
        parsed = fallback
    return max(parsed, 1)

