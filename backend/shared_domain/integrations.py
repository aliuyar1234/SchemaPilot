"""Disabled-by-default stubs for external integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.shared_domain.errors import DisabledIntegrationError


@dataclass(frozen=True)
class PolicyDecision:
    """Policy engine decision."""

    result: str
    reason: str


class PolicyEngineAdapter(Protocol):
    """Policy engine interface."""

    def evaluate(self, request_context: dict[str, object]) -> PolicyDecision:
        """Evaluate policy request."""


class IdentityProviderAdapter(Protocol):
    """Identity provider interface."""

    def authenticate(self, token: str) -> dict[str, object]:
        """Validate token and return identity context."""


class EmbeddingProvider(Protocol):
    """External embedding provider interface."""

    def embed(self, text: str) -> list[float]:
        """Generate vector embedding."""


class DisabledPolicyEngine:
    """Fail-closed policy adapter used when OPA integration is not enabled."""

    def evaluate(self, request_context: dict[str, object]) -> PolicyDecision:
        raise DisabledIntegrationError(
            "Policy engine integration is disabled.",
            details={"integration": "policy_engine", "request_context": request_context},
        )


class DisabledIdentityProvider:
    """Fail-closed identity provider adapter."""

    def authenticate(self, token: str) -> dict[str, object]:
        raise DisabledIntegrationError(
            "Identity provider integration is disabled.",
            details={"integration": "identity_provider", "token_present": bool(token)},
        )


class DisabledEmbeddingProvider:
    """Fail-closed embedding provider adapter."""

    def embed(self, text: str) -> list[float]:
        raise DisabledIntegrationError(
            "Embedding provider integration is disabled.",
            details={"integration": "embedding_provider", "input_length": len(text)},
        )
