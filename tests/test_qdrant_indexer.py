from __future__ import annotations

import pytest

from backend.shared_domain.embeddings_provider import DeterministicHashEmbeddingsProvider
from backend.shared_domain.errors import DisabledIntegrationError
from backend.workers.indexers.qdrant_indexer import (
    QdrantIndexingError,
    build_points_payload,
    index_documents_qdrant,
)


def test_build_points_payload_is_deterministic_and_sorted() -> None:
    provider = DeterministicHashEmbeddingsProvider(dimensions=4)
    points = build_points_payload(
        workspace_id="w1",
        corpus=[
            {"artifact_id": "b2", "dataset_id": "dataset-1", "text": "second"},
            {"artifact_id": "a1", "dataset_id": "dataset-1", "text": "first"},
        ],
        embeddings_provider=provider,
    )
    assert points[0]["id"] == "a1"
    assert points[1]["id"] == "b2"
    assert len(points[0]["vector"]) == 4


def test_index_documents_qdrant_raises_on_upsert_failure() -> None:
    provider = DeterministicHashEmbeddingsProvider(dimensions=4)

    def fake_request(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
        _ = (url, payload, timeout_ms)
        return {"status": "error"}

    with pytest.raises(QdrantIndexingError):
        index_documents_qdrant(
            workspace_id="w1",
            corpus=[{"artifact_id": "a1", "dataset_id": "dataset-1", "text": "invoice"}],
            qdrant_url="http://qdrant:6333",
            collection_name="schemapilot_docs",
            embeddings_provider=provider,
            request_fn=fake_request,
        )


def test_index_documents_qdrant_fails_when_embeddings_disabled() -> None:
    class DisabledProvider:
        def embed(self, text: str) -> list[float]:
            _ = text
            raise DisabledIntegrationError(
                "Embedding provider integration is disabled.",
                details={"integration": "embedding_provider"},
            )

    with pytest.raises(QdrantIndexingError):
        index_documents_qdrant(
            workspace_id="w1",
            corpus=[{"artifact_id": "a1", "dataset_id": "dataset-1", "text": "invoice"}],
            qdrant_url="http://qdrant:6333",
            collection_name="schemapilot_docs",
            embeddings_provider=DisabledProvider(),
            request_fn=lambda url, payload, timeout: {"status": "ok"},
        )

