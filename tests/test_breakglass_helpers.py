from __future__ import annotations

import pytest

from backend.control_plane.breakglass import (
    apply_breakglass_decision,
    build_breakglass_request_payload,
    is_breakglass_grant_expired,
    normalize_breakglass_ttl,
    required_approvals_for_profile,
)


def test_required_approvals_profile_defaults() -> None:
    assert required_approvals_for_profile("enterprise") == 2
    assert required_approvals_for_profile("team") == 1
    assert required_approvals_for_profile("starter") == 1


def test_normalize_breakglass_ttl_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        normalize_breakglass_ttl(ttl_value=0, max_ttl_seconds=3600)
    with pytest.raises(ValueError):
        normalize_breakglass_ttl(ttl_value=3601, max_ttl_seconds=3600)


def test_breakglass_decision_requires_two_approvals_for_enterprise() -> None:
    request_payload = build_breakglass_request_payload(
        workspace_id="w1",
        actor_id="user:analyst",
        requested_by="user:steward",
        ttl_seconds=300,
        required_approvals=2,
        now_epoch=1000,
    )
    first = apply_breakglass_decision(
        request_id="req-1",
        request_payload=request_payload,
        decision="approve",
        actor_id="user:steward",
        decision_reason="incident",
        now_epoch=1010,
    )
    assert first.request_payload["status"] == "pending"
    assert first.grant_payload is None
    second = apply_breakglass_decision(
        request_id="req-1",
        request_payload=first.request_payload,
        decision="approve",
        actor_id="user:admin",
        decision_reason="incident",
        now_epoch=1020,
    )
    assert second.request_payload["status"] == "active"
    assert second.grant_payload is not None
    assert second.grant_payload["request_id"] == "req-1"


def test_breakglass_decision_reject_path() -> None:
    request_payload = build_breakglass_request_payload(
        workspace_id="w1",
        actor_id="user:analyst",
        requested_by="user:steward",
        ttl_seconds=300,
        required_approvals=1,
        now_epoch=1000,
    )
    result = apply_breakglass_decision(
        request_id="req-2",
        request_payload=request_payload,
        decision="reject",
        actor_id="user:steward",
        decision_reason="insufficient_justification",
        now_epoch=1010,
    )
    assert result.request_payload["status"] == "rejected"
    assert result.grant_payload is None


def test_breakglass_grant_expiry() -> None:
    grant_payload = {"request_id": "req-3", "expires_epoch": 20}
    assert is_breakglass_grant_expired(grant_payload=grant_payload, now_epoch=21) is True
    assert is_breakglass_grant_expired(grant_payload=grant_payload, now_epoch=20) is False
