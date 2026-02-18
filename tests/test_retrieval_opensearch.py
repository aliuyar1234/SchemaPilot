from __future__ import annotations

from backend.gateway.retrieval_opensearch import (
    OpenSearchUnavailableError,
    search_opensearch_documents,
)


def test_search_opensearch_documents_filters_by_allowed_datasets() -> None:
    def fake_request(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
        assert url.endswith("/schemapilot_docs/_search")
        assert timeout_ms == 2500
        assert payload["size"] == 5
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "artifact_id": "a1",
                            "dataset_id": "dataset-1",
                            "text": "invoice for acme",
                            "citation": "artifact:a1",
                        }
                    },
                    {
                        "_source": {
                            "artifact_id": "a2",
                            "dataset_id": "dataset-2",
                            "text": "not allowed",
                            "citation": "artifact:a2",
                        }
                    },
                ]
            }
        }

    results = search_opensearch_documents(
        query_text="invoice",
        workspace_id="w1",
        allowed_dataset_ids={"dataset-1"},
        base_url="http://opensearch:9200",
        index_name="schemapilot_docs",
        timeout_ms=2500,
        max_results=5,
        request_fn=fake_request,
    )
    assert len(results) == 1
    assert results[0]["artifact_id"] == "a1"
    assert results[0]["dataset_id"] == "dataset-1"


def test_search_opensearch_documents_returns_empty_on_blank_query_or_entitlements() -> None:
    results_blank = search_opensearch_documents(
        query_text="",
        workspace_id="w1",
        allowed_dataset_ids={"dataset-1"},
        base_url="http://opensearch:9200",
        index_name="schemapilot_docs",
    )
    results_no_entitlements = search_opensearch_documents(
        query_text="invoice",
        workspace_id="w1",
        allowed_dataset_ids=set(),
        base_url="http://opensearch:9200",
        index_name="schemapilot_docs",
    )
    assert results_blank == []
    assert results_no_entitlements == []


def test_search_opensearch_documents_propagates_unavailable_error() -> None:
    def failing_request(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
        _ = (url, payload, timeout_ms)
        raise OpenSearchUnavailableError("opensearch_unavailable")

    try:
        search_opensearch_documents(
            query_text="invoice",
            workspace_id="w1",
            allowed_dataset_ids={"dataset-1"},
            base_url="http://opensearch:9200",
            index_name="schemapilot_docs",
            request_fn=failing_request,
        )
    except OpenSearchUnavailableError as exc:
        assert str(exc) == "opensearch_unavailable"
    else:  # pragma: no cover - defensive
        raise AssertionError("expected OpenSearchUnavailableError")
