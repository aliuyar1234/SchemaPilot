"""Bootstrap worker stubs for external integrations and task types."""

from __future__ import annotations

from backend.shared_domain.errors import DisabledIntegrationError


def run_discovery_stub() -> dict[str, object]:
    """Placeholder discovery worker behavior."""
    return {"status": "queued", "task": "discover"}


def run_opa_policy_adapter_stub() -> dict[str, object]:
    """Disabled-by-default OPA adapter stub."""
    raise DisabledIntegrationError(
        "OPA integration is disabled by default.",
        details={"integration": "opa", "enabled": False},
    )


def run_identity_provider_stub() -> dict[str, object]:
    """Disabled-by-default identity provider stub."""
    raise DisabledIntegrationError(
        "External identity provider integration is disabled by default.",
        details={"integration": "identity_provider", "enabled": False},
    )


def run_embedding_provider_stub() -> dict[str, object]:
    """Disabled-by-default embedding provider stub."""
    raise DisabledIntegrationError(
        "External embedding integration is disabled by default.",
        details={"integration": "embedding_provider", "enabled": False},
    )
