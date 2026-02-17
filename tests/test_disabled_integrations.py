from __future__ import annotations

import pytest

from backend.shared_domain.errors import DisabledIntegrationError
from backend.shared_domain.integrations import (
    DisabledEmbeddingProvider,
    DisabledIdentityProvider,
    DisabledPolicyEngine,
)


def test_disabled_policy_engine_raises() -> None:
    adapter = DisabledPolicyEngine()
    with pytest.raises(DisabledIntegrationError):
        adapter.evaluate({"resource": "gold.fact_invoices"})


def test_disabled_identity_provider_raises() -> None:
    adapter = DisabledIdentityProvider()
    with pytest.raises(DisabledIntegrationError):
        adapter.authenticate("token")


def test_disabled_embedding_provider_raises() -> None:
    adapter = DisabledEmbeddingProvider()
    with pytest.raises(DisabledIntegrationError):
        adapter.embed("hello")
