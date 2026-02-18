from __future__ import annotations

from backend.gateway.retrieval_qdrant import QdrantUnavailableError, search_qdrant_documents


def test_search_qdrant_documents_filters_by_allowed_datasets() -> None:
    def fake_request(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
        assert url.endswith("/collections/schemapilot_docs/points/search")
        assert timeout_ms == 2500
        assert payload["limit"] == 5
        return {
            "result": [
                {
                    "payload": {
                        "artifact_id": "a1",
                        "dataset_id": "dataset-1",
                        "text": "invoice acme",
                        "citation": "artifact:a1",
                    }
                },
                {
                    "payload": {
                        "artifact_id": "a2",
                        "dataset_id": "dataset-2",
                        "text": "not allowed",
                        "citation": "artifact:a2",
                    }
                },
            ]
        }

    results = search_qdrant_documents(
        query_vector=[0.1, 0.2, 0.3],
        workspace_id="w1",
        allowed_dataset_ids={"dataset-1"},
        base_url="http://qdrant:6333",
        collection_name="schemapilot_docs",
        timeout_ms=2500,
        max_results=5,
        request_fn=fake_request,
    )
    assert len(results) == 1
    assert results[0]["dataset_id"] == "dataset-1"
    assert results[0]["artifact_id"] == "a1"


def test_search_qdrant_documents_returns_empty_for_missing_vector_or_entitlements() -> None:
    no_vector = search_qdrant_documents(
        query_vector=[],
        workspace_id="w1",
        allowed_dataset_ids={"dataset-1"},
        base_url="http://qdrant:6333",
        collection_name="schemapilot_docs",
    )
    no_entitlements = search_qdrant_documents(
        query_vector=[0.1],
        workspace_id="w1",
        allowed_dataset_ids=set(),
        base_url="http://qdrant:6333",
        collection_name="schemapilot_docs",
    )
    assert no_vector == []
    assert no_entitlements == []


def test_search_qdrant_documents_propagates_unavailable_error() -> None:
    def failing_request(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
        _ = (url, payload, timeout_ms)
        raise QdrantUnavailableError("qdrant_unavailable")

    try:
        search_qdrant_documents(
            query_vector=[0.1],
            workspace_id="w1",
            allowed_dataset_ids={"dataset-1"},
            base_url="http://qdrant:6333",
            collection_name="schemapilot_docs",
            request_fn=failing_request,
        )
    except QdrantUnavailableError as exc:
        assert str(exc) == "qdrant_unavailable"
    else:  # pragma: no cover - defensive
        raise AssertionError("expected QdrantUnavailableError")

