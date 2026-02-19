"""Break-glass request/grant lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BREAKGLASS_TTL_SECONDS = 900
DEFAULT_BREAKGLASS_MAX_TTL_SECONDS = 3600


@dataclass(frozen=True)
class BreakglassDecisionResult:
    """Result payload for one break-glass decision."""

    request_payload: dict[str, object]
    grant_payload: dict[str, object] | None


def required_approvals_for_profile(profile: str) -> int:
    """Return required approval count for one workspace profile."""

    normalized = profile.strip().lower()
    if normalized == "enterprise":
        return 2
    return 1


def normalize_breakglass_ttl(*, ttl_value: object, max_ttl_seconds: int) -> int:
    """Normalize and validate break-glass TTL seconds."""

    ttl_seconds = _coerce_int(ttl_value, default=DEFAULT_BREAKGLASS_TTL_SECONDS)
    if ttl_seconds <= 0 or ttl_seconds > max_ttl_seconds:
        raise ValueError("invalid_breakglass_ttl")
    return ttl_seconds


def build_breakglass_request_payload(
    *,
    workspace_id: str,
    actor_id: str,
    requested_by: str,
    ttl_seconds: int,
    required_approvals: int,
    now_epoch: int,
) -> dict[str, object]:
    """Build deterministic break-glass request payload."""

    return {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "ttl_seconds": ttl_seconds,
        "required_approvals": max(required_approvals, 1),
        "status": "pending",
        "approvals": [],
        "requested_by": requested_by,
        "created_at_epoch": now_epoch,
    }


def apply_breakglass_decision(
    *,
    request_id: str,
    request_payload: dict[str, object],
    decision: str,
    actor_id: str,
    decision_reason: str,
    now_epoch: int,
) -> BreakglassDecisionResult:
    """Apply approve/reject decision and optionally produce active grant payload."""

    status = str(request_payload.get("status", "pending")).strip().lower()
    if status in {"revoked", "expired"}:
        raise ValueError(f"breakglass_{status}")
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        raise ValueError("invalid_decision")

    updated = dict(request_payload)
    approvals_raw = updated.get("approvals", [])
    approvals = approvals_raw if isinstance(approvals_raw, list) else []
    deduped_approvals = sorted({str(item) for item in approvals if str(item).strip()})

    if normalized_decision == "approve":
        if actor_id not in deduped_approvals:
            deduped_approvals.append(actor_id)
            deduped_approvals = sorted({str(item) for item in deduped_approvals if str(item)})
    else:
        updated["status"] = "rejected"

    updated["approvals"] = deduped_approvals
    updated["last_decision_actor_id"] = actor_id
    updated["last_decision_reason"] = decision_reason
    updated["last_decision_at_epoch"] = now_epoch

    required_approvals = _coerce_int(updated.get("required_approvals"), default=1)
    grant_payload: dict[str, object] | None = None
    if normalized_decision == "approve" and len(deduped_approvals) >= max(required_approvals, 1):
        ttl_seconds = _coerce_int(
            updated.get("ttl_seconds"),
            default=DEFAULT_BREAKGLASS_TTL_SECONDS,
        )
        expires_epoch = now_epoch + max(ttl_seconds, 1)
        updated["status"] = "active"
        updated["active_from_epoch"] = now_epoch
        updated["expires_epoch"] = expires_epoch
        grant_payload = {
            "request_id": request_id,
            "workspace_id": str(updated.get("workspace_id", "")),
            "actor_id": str(updated.get("actor_id", "")),
            "status": "active",
            "expires_epoch": expires_epoch,
        }
    return BreakglassDecisionResult(request_payload=updated, grant_payload=grant_payload)


def mark_breakglass_revoked(
    *,
    request_payload: dict[str, object],
    revoked_by: str,
    now_epoch: int,
    reason: str,
) -> dict[str, object]:
    """Mark one break-glass request as revoked."""

    updated = dict(request_payload)
    updated["status"] = "revoked"
    updated["revoked_by"] = revoked_by
    updated["revoked_reason"] = reason
    updated["revoked_at_epoch"] = now_epoch
    return updated


def mark_breakglass_expired(
    *,
    request_payload: dict[str, object],
    now_epoch: int,
    expired_by: str = "system:auto",
) -> dict[str, object]:
    """Mark one break-glass request as expired."""

    updated = dict(request_payload)
    updated["status"] = "expired"
    updated["expired_by"] = expired_by
    updated["expired_at_epoch"] = now_epoch
    return updated


def is_breakglass_grant_expired(*, grant_payload: dict[str, object], now_epoch: int) -> bool:
    """Return whether one active grant has expired."""

    expires_epoch = _coerce_int(grant_payload.get("expires_epoch"), default=0)
    return bool(expires_epoch and expires_epoch < now_epoch)


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default
