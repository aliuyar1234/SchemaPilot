from __future__ import annotations

from backend.shared_domain.target_db.adapters.base import TargetDbProfileConfig
from backend.workers.db_builder.validate_external_db import validate_external_target_db_profile


def _profile(
    *,
    connection: dict[str, object],
    credential_refs: dict[str, object],
) -> TargetDbProfileConfig:
    return TargetDbProfileConfig(
        workspace_id="ws_1",
        target_db_id="tdb_1",
        db_type="postgres",
        mode="external",
        connection=connection,
        credential_refs=credential_refs,
    )


def test_external_validator_requires_connection_and_credentials() -> None:
    profile = _profile(connection={"host": "db"}, credential_refs={"reader": "secret://local/r"})
    result = validate_external_target_db_profile(
        profile=profile,
        profile_name="serving-db",
        desired_config_hash="sha256:dummy",
    )
    assert result.ok is False
    errors = result.details["errors"]
    assert "missing_connection_field:port" in errors
    assert "missing_connection_field:database" in errors
    assert "missing_credential_ref:writer" in errors


def test_external_validator_detects_hash_drift() -> None:
    profile = _profile(
        connection={"host": "db", "port": 5432, "database": "analytics"},
        credential_refs={
            "reader": "secret://local/r",
            "writer": "secret://local/w",
        },
    )
    result = validate_external_target_db_profile(
        profile=profile,
        profile_name="serving-db",
        desired_config_hash="sha256:deadbeef",
    )
    assert result.ok is False
    assert result.details["drift_detected"] is True
    assert "desired_config_hash_mismatch" in result.details["errors"]
