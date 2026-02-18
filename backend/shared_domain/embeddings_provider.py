"""Embedding provider adapters with fail-closed defaults."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from backend.shared_domain.errors import DisabledIntegrationError, StartupConfigurationError

SUPPORTED_EMBEDDINGS_PROVIDERS = {"disabled", "hash"}


class EmbeddingsProvider(Protocol):
    """Embedding provider contract used by retrieval/index adapters."""

    def embed(self, text: str) -> list[float]:
        """Return deterministic embedding values for the provided text."""


class DisabledEmbeddingsProvider:
    """Fail-closed provider used when embeddings are not enabled."""

    def embed(self, text: str) -> list[float]:
        raise DisabledIntegrationError(
            "Embedding provider integration is disabled.",
            details={"integration": "embedding_provider", "input_length": len(text)},
        )


@dataclass(frozen=True)
class DeterministicHashEmbeddingsProvider:
    """Local deterministic provider for optional vector retrieval/indexing paths."""

    dimensions: int = 16

    def embed(self, text: str) -> list[float]:
        base = text if text else "<empty>"
        seed = base.encode("utf-8")
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            counter += 1
            for value in digest:
                # Normalize deterministic byte values to [-1, 1].
                values.append((value / 127.5) - 1.0)
                if len(values) >= self.dimensions:
                    break
        return values


def load_embeddings_provider(*, provider_name: str, dimensions: int) -> EmbeddingsProvider:
    """Load configured embeddings provider with fail-closed behavior."""
    name = provider_name.strip().lower()
    if name == "disabled":
        return DisabledEmbeddingsProvider()
    if name == "hash":
        return DeterministicHashEmbeddingsProvider(dimensions=max(1, dimensions))
    raise StartupConfigurationError(
        "Unsupported embeddings provider.",
        details={
            "embeddings_provider": provider_name,
            "supported_embeddings_providers": sorted(SUPPORTED_EMBEDDINGS_PROVIDERS),
        },
    )
