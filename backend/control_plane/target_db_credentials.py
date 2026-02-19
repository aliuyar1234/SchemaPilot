"""Control-plane helpers for target DB credential rotation requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_DUAL_VALIDITY_WINDOW_SECONDS = 300
REQUIRED_NON_MANAGED_ROTATION_ROLES = ("reader", "writer")


@dataclass(frozen=True)
class RotationPrerequisiteStatus:
    """Prerequisite status for target DB credential rotation."""

    ok: bool
    required_roles: tuple[str, ...]
    missing_roles: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "required_roles": list(self.required_roles),
            "missing_roles": list(self.missing_roles),
        }


def evaluate_rotation_prerequisites(profile: dict[str, object]) -> RotationPrerequisiteStatus:
    """Evaluate whether a target-db profile can start credential rotation."""

    db_type = str(profile.get("db_type", "")).strip().lower()
    mode = str(profile.get("mode", "")).strip().lower()
    if db_type == "postgres" and mode == "managed":
        return RotationPrerequisiteStatus(ok=True, required_roles=(), missing_roles=())

    refs_raw = profile.get("credential_refs", {})
    refs = refs_raw if isinstance(refs_raw, dict) else {}
    missing_roles = tuple(
        role for role in REQUIRED_NON_MANAGED_ROTATION_ROLES if not str(refs.get(role, "")).strip()
    )
    return RotationPrerequisiteStatus(
        ok=not missing_roles,
        required_roles=REQUIRED_NON_MANAGED_ROTATION_ROLES,
        missing_roles=missing_roles,
    )


def build_rotation_run_input_refs(
    *,
    target_db_id: str,
    rotation_reason: str,
    requested_by: str,
    dual_validity_window_seconds: int = DEFAULT_DUAL_VALIDITY_WINDOW_SECONDS,
) -> dict[str, Any]:
    """Build deterministic run input payload for credential-rotation runs."""

    window_seconds = max(int(dual_validity_window_seconds), 0)
    reason = rotation_reason.strip() or "operator_requested"
    return {
        "target_db_id": target_db_id,
        "rotation_reason": reason,
        "requested_by": requested_by,
        "dual_validity_window_seconds": window_seconds,
    }
