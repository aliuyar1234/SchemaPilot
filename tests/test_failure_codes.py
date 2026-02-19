from __future__ import annotations

from backend.shared_domain.failure_codes import (
    FAILURE_CODE_VERSION,
    attach_failure_metadata,
    classify_failure,
    list_failure_definitions,
    resolve_failure_metadata,
)


def test_classify_failure_maps_strict_completeness() -> None:
    mapped = classify_failure(legacy_error_code="strict_ingest_completeness_failed")
    assert mapped.failure_code == "FC-0003_STRICT_COMPLETENESS"
    assert mapped.failure_category == "strict_completeness"


def test_classify_failure_maps_timeout() -> None:
    mapped = classify_failure(legacy_error_code="worker_step_timeout_exceeded")
    assert mapped.failure_code == "FC-0007_TIMEOUT"
    assert mapped.failure_category == "timeout"


def test_resolve_failure_metadata_uses_unknown_for_unmapped_codes() -> None:
    metadata = resolve_failure_metadata(
        details={"error": "unexpected runtime issue"},
        legacy_error_code="unexpected_runtime_issue",
    )
    assert metadata is not None
    assert metadata["failure_code"] == "FC-0000_UNKNOWN"
    assert metadata["failure_category"] == "unknown"
    assert metadata["failure_code_version"] == FAILURE_CODE_VERSION


def test_attach_failure_metadata_preserves_existing_canonical_code() -> None:
    payload = attach_failure_metadata(
        details={"failure_code": "FC-0002_AUTHZ"},
        legacy_error_code="strict_ingest_completeness_failed",
    )
    assert payload["failure_code"] == "FC-0002_AUTHZ"
    assert payload["failure_category"] == "authz"
    assert payload["failure_code_version"] == FAILURE_CODE_VERSION


def test_failure_code_registry_starts_with_unknown() -> None:
    definitions = list_failure_definitions()
    assert definitions[0].failure_code == "FC-0000_UNKNOWN"
    assert len({definition.failure_code for definition in definitions}) == len(definitions)
