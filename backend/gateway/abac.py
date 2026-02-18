"""ABAC evaluation and masking helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.shared_domain.errors import DisabledIntegrationError


@dataclass(frozen=True)
class AbacDecision:
    """ABAC decision result."""

    allow: bool
    reason: str
    row_filter: tuple[str, str] | None
    masks: dict[str, str]


def evaluate_internal_abac(
    *, actor: dict[str, object], resource_attributes: dict[str, object]
) -> AbacDecision:
    """Evaluate internal ABAC policy."""
    attributes_raw = actor.get("attributes")
    attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
    actor_region = str(attributes.get("region", ""))
    resource_region = str(resource_attributes.get("region", ""))
    if resource_region and actor_region and actor_region != resource_region:
        return AbacDecision(
            allow=False,
            reason="region_mismatch",
            row_filter=None,
            masks={},
        )
    masks: dict[str, str] = {}
    roles_raw = actor.get("roles", [])
    roles = roles_raw if isinstance(roles_raw, list) else []
    if "analyst" in roles:
        masks = {"email": "partial_reveal"}
    row_filter: tuple[str, str] | None = None
    if actor_region:
        row_filter = ("region", actor_region)
    return AbacDecision(
        allow=True,
        reason="internal_abac_allow",
        row_filter=row_filter,
        masks=masks,
    )


class OpaAdapter:
    """Optional OPA adapter; disabled by default in bootstrap."""

    def evaluate(self, _input_payload: dict[str, object]) -> AbacDecision:
        raise DisabledIntegrationError(
            "OPA ABAC integration is disabled by default.",
            details={"integration": "opa_abac"},
        )


def evaluate_abac(
    *,
    actor: dict[str, object],
    resource_attributes: dict[str, object],
    mode: str = "internal",
    opa_adapter: OpaAdapter | None = None,
) -> AbacDecision:
    """Evaluate ABAC with fail-closed fallback when OPA is enabled."""
    normalized_mode = mode.lower()
    if normalized_mode != "opa":
        return evaluate_internal_abac(actor=actor, resource_attributes=resource_attributes)
    adapter = opa_adapter or OpaAdapter()
    try:
        return adapter.evaluate({"actor": actor, "resource_attributes": resource_attributes})
    except DisabledIntegrationError:
        return AbacDecision(
            allow=False,
            reason="opa_unavailable",
            row_filter=None,
            masks={},
        )


def apply_mask(value: object, mode: str) -> object:
    """Apply column mask mode."""
    if mode == "null":
        return None
    if mode == "hash":
        return hashlib.sha256(str(value).encode()).hexdigest()
    if mode == "partial_reveal":
        text = str(value)
        if len(text) <= 2:
            return "*" * len(text)
        return text[:1] + ("*" * (len(text) - 2)) + text[-1:]
    return value
