"""Semantic schema version normalization and compatibility helpers."""

from __future__ import annotations

DEFAULT_COMPAT_MAX_RUNTIME_VERSION = "1.0.0"


def normalize_semantic_schema_version(schema_version: str) -> str:
    """Return deterministic semantic schema version token."""

    normalized = schema_version.strip().lower()
    return normalized or "v1"


def default_compat_range(*, runtime_version: str) -> str:
    """Return deterministic runtime compatibility range string."""

    normalized_runtime = runtime_version.strip() or "0.1.0"
    return f">={normalized_runtime},<{DEFAULT_COMPAT_MAX_RUNTIME_VERSION}"
