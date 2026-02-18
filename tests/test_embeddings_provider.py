from __future__ import annotations

import pytest

from backend.shared_domain.embeddings_provider import (
    DeterministicHashEmbeddingsProvider,
    load_embeddings_provider,
)
from backend.shared_domain.errors import DisabledIntegrationError, StartupConfigurationError


def test_hash_embeddings_provider_is_deterministic() -> None:
    provider = DeterministicHashEmbeddingsProvider(dimensions=8)
    first = provider.embed("invoice 42")
    second = provider.embed("invoice 42")
    third = provider.embed("invoice 43")
    assert first == second
    assert len(first) == 8
    assert third != first


def test_disabled_embeddings_provider_fails_closed() -> None:
    provider = load_embeddings_provider(provider_name="disabled", dimensions=8)
    with pytest.raises(DisabledIntegrationError):
        provider.embed("invoice")


def test_unknown_embeddings_provider_is_rejected() -> None:
    with pytest.raises(StartupConfigurationError):
        load_embeddings_provider(provider_name="unknown", dimensions=8)

