from __future__ import annotations

from backend.workers.run_processor import _validate_connector_scope_secret_refs


def test_connector_scope_validation_accepts_secret_refs() -> None:
    _validate_connector_scope_secret_refs(
        scope={
            "root_path": "/exports",
            "credentials_ref": "secret://vault/sharepoint/oauth",
            "api_key_ref": "secret://vault/sharepoint/key",
        },
        source_type="sharepoint",
    )


def test_connector_scope_validation_rejects_plain_secret_values() -> None:
    try:
        _validate_connector_scope_secret_refs(
            scope={
                "root_path": "/exports",
                "password": "super-secret",
                "token": "abc",
            },
            source_type="sharepoint",
        )
    except ValueError as exc:
        assert "connector_secret_ref_required:sharepoint" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
