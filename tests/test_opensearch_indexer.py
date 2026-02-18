from __future__ import annotations

from backend.workers.indexers.opensearch_indexer import (
    OpenSearchIndexingError,
    build_bulk_payload,
    index_documents_opensearch,
)


def test_build_bulk_payload_is_deterministic_and_sorted() -> None:
    payload = build_bulk_payload(
        workspace_id="w1",
        index_name="schemapilot_docs",
        corpus=[
            {"artifact_id": "b2", "dataset_id": "dataset-1", "text": "second"},
            {"artifact_id": "a1", "dataset_id": "dataset-1", "text": "first"},
        ],
    )
    decoded = payload.decode("utf-8")
    lines = [line for line in decoded.splitlines() if line.strip()]
    assert '"artifact_id": "a1"' in lines[1]
    assert '"artifact_id": "b2"' in lines[3]


def test_index_documents_opensearch_raises_on_bulk_errors() -> None:
    def fake_request(url: str, payload: bytes, timeout_ms: int) -> dict[str, object]:
        _ = (url, payload, timeout_ms)
        return {"errors": True}

    try:
        index_documents_opensearch(
            workspace_id="w1",
            index_name="schemapilot_docs",
            opensearch_url="http://opensearch:9200",
            corpus=[{"artifact_id": "a1", "dataset_id": "dataset-1", "text": "invoice"}],
            request_fn=fake_request,
        )
    except OpenSearchIndexingError as exc:
        assert str(exc) == "opensearch_bulk_errors"
    else:  # pragma: no cover - defensive
        raise AssertionError("expected OpenSearchIndexingError")
