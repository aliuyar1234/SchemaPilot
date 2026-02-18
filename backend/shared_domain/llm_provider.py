"""LLM provider abstraction for optional AI service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.shared_domain.errors import DisabledIntegrationError, StartupConfigurationError


class LLMProvider(Protocol):
    """LLM provider contract for AI assistant modules."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate a completion string."""


class DisabledLLMProvider:
    """Fail-closed provider used when AI provider is disabled."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG002
        raise DisabledIntegrationError(
            "AI provider integration is disabled.",
            details={"integration": "llm_provider"},
        )


@dataclass(frozen=True)
class MockLLMProvider:
    """Deterministic mock provider for local development and tests."""

    prefix: str = "mock"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        system_head = system_prompt.strip().splitlines()[0] if system_prompt.strip() else ""
        return f"{self.prefix}:{system_head}:{user_prompt.strip()[:180]}"


def load_llm_provider(provider_name: str) -> LLMProvider:
    """Load configured provider."""
    normalized = provider_name.strip().lower()
    if normalized == "disabled":
        return DisabledLLMProvider()
    if normalized == "mock":
        return MockLLMProvider()
    raise StartupConfigurationError(
        "Unsupported AI provider.",
        details={"ai_provider": provider_name},
    )

