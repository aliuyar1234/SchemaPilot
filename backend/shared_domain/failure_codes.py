"""Canonical run-step failure taxonomy and deterministic mapping helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

FAILURE_CODE_VERSION = "v1"


@dataclass(frozen=True)
class FailureDefinition:
    """Stable failure definition used in run-step diagnostics."""

    failure_code: str
    failure_category: str
    operator_hint_ref: str


# Stable FC registry. New codes must append; never renumber existing entries.
_DEFINITIONS: tuple[FailureDefinition, ...] = (
    FailureDefinition(
        failure_code="FC-0000_UNKNOWN",
        failure_category="unknown",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0000_unknown",
    ),
    FailureDefinition(
        failure_code="FC-0001_SECRETS",
        failure_category="secrets",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0001_secrets",
    ),
    FailureDefinition(
        failure_code="FC-0002_AUTHZ",
        failure_category="authz",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0002_authz",
    ),
    FailureDefinition(
        failure_code="FC-0003_STRICT_COMPLETENESS",
        failure_category="strict_completeness",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0003_strict_completeness",
    ),
    FailureDefinition(
        failure_code="FC-0004_DRIFT",
        failure_category="drift",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0004_drift",
    ),
    FailureDefinition(
        failure_code="FC-0005_SCHEMA_MISMATCH",
        failure_category="schema_mismatch",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0005_schema_mismatch",
    ),
    FailureDefinition(
        failure_code="FC-0006_ENGINE_UNAVAILABLE",
        failure_category="engine_unavailable",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0006_engine_unavailable",
    ),
    FailureDefinition(
        failure_code="FC-0007_TIMEOUT",
        failure_category="timeout",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0007_timeout",
    ),
    FailureDefinition(
        failure_code="FC-0008_SANDBOX_VIOLATION",
        failure_category="sandbox_violation",
        operator_hint_ref="docs/runbook/FAILURE_CODES.md#fc-0008_sandbox_violation",
    ),
)

_DEFINITION_BY_CODE: dict[str, FailureDefinition] = {
    definition.failure_code: definition for definition in _DEFINITIONS
}

_LEGACY_CODE_TO_FAILURE_CODE: dict[str, str] = {
    "strict_ingest_completeness_failed": "FC-0003_STRICT_COMPLETENESS",
    "worker_step_timeout_exceeded": "FC-0007_TIMEOUT",
    "policy_denied": "FC-0002_AUTHZ",
    "dataset_not_allowed": "FC-0002_AUTHZ",
}

_HEURISTIC_MATCHERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("secret", "credential", "jwks", "oidc_key"), "FC-0001_SECRETS"),
    (("policy_denied", "forbidden", "unauthorized", "authz", "auth"), "FC-0002_AUTHZ"),
    (("strict_ingest", "completeness"), "FC-0003_STRICT_COMPLETENESS"),
    (("drift",), "FC-0004_DRIFT"),
    (("schema", "contract_failure"), "FC-0005_SCHEMA_MISMATCH"),
    (("engine_unavailable", "trino", "duckdb", "target_db"), "FC-0006_ENGINE_UNAVAILABLE"),
    (("timeout", "timed_out"), "FC-0007_TIMEOUT"),
    (("sandbox", "allowlist", "plugin"), "FC-0008_SANDBOX_VIOLATION"),
)


def list_failure_definitions() -> tuple[FailureDefinition, ...]:
    """Return stable failure definitions in canonical order."""

    return _DEFINITIONS


def classify_failure(
    *, legacy_error_code: str | None = None, message: str | None = None
) -> FailureDefinition:
    """Map legacy errors/messages into the canonical FC taxonomy."""

    normalized_code = _normalize(legacy_error_code)
    if normalized_code:
        mapped = _LEGACY_CODE_TO_FAILURE_CODE.get(normalized_code)
        if mapped is not None:
            return _DEFINITION_BY_CODE[mapped]

    normalized_parts = (_normalize(legacy_error_code), _normalize(message))
    haystack = " ".join(part for part in normalized_parts if part)
    for tokens, failure_code in _HEURISTIC_MATCHERS:
        if any(token in haystack for token in tokens):
            return _DEFINITION_BY_CODE[failure_code]

    return _DEFINITION_BY_CODE["FC-0000_UNKNOWN"]


def attach_failure_metadata(
    *,
    details: Mapping[str, object] | None,
    legacy_error_code: str | None = None,
    message: str | None = None,
) -> dict[str, object]:
    """Return details enriched with canonical failure metadata."""

    payload = dict(details or {})
    existing = _existing_definition(payload)
    definition = existing or classify_failure(legacy_error_code=legacy_error_code, message=message)
    payload["failure_code"] = definition.failure_code
    payload["failure_category"] = definition.failure_category
    payload["operator_hint_ref"] = definition.operator_hint_ref
    payload["failure_code_version"] = FAILURE_CODE_VERSION
    if legacy_error_code:
        payload.setdefault("legacy_error_code", legacy_error_code)
    return payload


def resolve_failure_metadata(
    *,
    details: Mapping[str, object] | None,
    legacy_error_code: str | None = None,
    message: str | None = None,
) -> dict[str, str] | None:
    """Resolve canonical metadata for failed rows while preserving compatibility."""

    has_failure_signal = bool(legacy_error_code) or _has_existing_failure_code(details)
    if not has_failure_signal:
        return None
    payload = attach_failure_metadata(
        details=details,
        legacy_error_code=legacy_error_code,
        message=message,
    )
    return {
        "failure_code": str(payload["failure_code"]),
        "failure_category": str(payload["failure_category"]),
        "operator_hint_ref": str(payload["operator_hint_ref"]),
        "failure_code_version": str(payload["failure_code_version"]),
    }


def _normalize(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
    return normalized


def _has_existing_failure_code(details: Mapping[str, object] | None) -> bool:
    if not isinstance(details, Mapping):
        return False
    existing = details.get("failure_code")
    return isinstance(existing, str) and existing in _DEFINITION_BY_CODE


def _existing_definition(details: Mapping[str, object]) -> FailureDefinition | None:
    existing = details.get("failure_code")
    if isinstance(existing, str):
        return _DEFINITION_BY_CODE.get(existing)
    return None
