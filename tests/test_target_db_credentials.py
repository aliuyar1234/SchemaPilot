from __future__ import annotations

from backend.control_plane.target_db_credentials import (
    build_rotation_run_input_refs,
    evaluate_rotation_prerequisites,
)


def test_rotation_prerequisites_allow_managed_postgres_without_existing_refs() -> None:
    profile = {
        "db_type": "postgres",
        "mode": "managed",
        "credential_refs": {},
    }
    status = evaluate_rotation_prerequisites(profile)
    assert status.ok is True
    assert status.missing_roles == ()


def test_rotation_prerequisites_fail_when_non_managed_missing_reader_writer() -> None:
    profile = {
        "db_type": "postgres",
        "mode": "external",
        "credential_refs": {"reader": "secret://r"},
    }
    status = evaluate_rotation_prerequisites(profile)
    assert status.ok is False
    assert status.missing_roles == ("writer",)


def test_rotation_input_payload_is_deterministic() -> None:
    payload = build_rotation_run_input_refs(
        target_db_id="target-1",
        rotation_reason="ops-drill",
        requested_by="user:ops",
        dual_validity_window_seconds=600,
    )
    assert payload["target_db_id"] == "target-1"
    assert payload["rotation_reason"] == "ops-drill"
    assert payload["dual_validity_window_seconds"] == 600
