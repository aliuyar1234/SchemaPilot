from __future__ import annotations

from backend.gateway.abac import apply_mask, evaluate_abac, evaluate_internal_abac


def test_internal_abac_denies_region_mismatch() -> None:
    decision = evaluate_internal_abac(
        actor={"roles": ["analyst"], "attributes": {"region": "eu"}},
        resource_attributes={"region": "us"},
    )
    assert decision.allow is False
    assert decision.reason == "region_mismatch"


def test_masking_modes() -> None:
    assert apply_mask("alice@example.com", "partial_reveal") != "alice@example.com"
    assert apply_mask("secret", "hash") != "secret"
    assert apply_mask("secret", "null") is None


def test_opa_mode_denies_when_adapter_disabled() -> None:
    decision = evaluate_abac(
        actor={"roles": ["analyst"], "attributes": {"region": "eu"}},
        resource_attributes={"region": "eu"},
        mode="opa",
    )
    assert decision.allow is False
    assert decision.reason == "opa_unavailable"
