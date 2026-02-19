"""External target-db validation helpers (least-privilege + config drift)."""

from __future__ import annotations

from backend.shared_domain.target_db.adapters.base import TargetDbProfileConfig, ValidationResult
from backend.shared_domain.target_db.hash import target_db_profile_hash

REQUIRED_CONNECTION_FIELDS = ("host", "port", "database")
REQUIRED_CREDENTIAL_REFS = ("reader", "writer")


def validate_external_target_db_profile(
    *,
    profile: TargetDbProfileConfig,
    profile_name: str,
    desired_config_hash: str,
) -> ValidationResult:
    """Validate external profile config and deterministic desired hash."""
    errors: list[str] = []
    if profile.mode != "external":
        errors.append("mode_must_be_external")
    for field in REQUIRED_CONNECTION_FIELDS:
        value = profile.connection.get(field)
        if value is None or not str(value).strip():
            errors.append(f"missing_connection_field:{field}")
    for ref_name in REQUIRED_CREDENTIAL_REFS:
        value = profile.credential_refs.get(ref_name)
        if value is None or not str(value).strip():
            errors.append(f"missing_credential_ref:{ref_name}")

    expected_hash = target_db_profile_hash(
        workspace_id=profile.workspace_id,
        name=profile_name,
        db_type=profile.db_type,
        mode=profile.mode,
        connection=profile.connection,
        credential_refs=profile.credential_refs,
    )
    drift_detected = bool(desired_config_hash) and expected_hash != desired_config_hash
    if drift_detected:
        errors.append("desired_config_hash_mismatch")

    return ValidationResult(
        ok=not errors,
        details={
            "db_type": profile.db_type,
            "mode": profile.mode,
            "drift_detected": drift_detected,
            "expected_hash": expected_hash,
            "desired_config_hash": desired_config_hash,
            "errors": errors,
        },
    )
