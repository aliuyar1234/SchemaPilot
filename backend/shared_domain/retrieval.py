"""Shared retrieval filtering helpers."""

from __future__ import annotations


def retrieve_documents(
    *,
    query_text: str,
    corpus: list[dict[str, object]],
    allowed_dataset_ids: set[str],
) -> list[dict[str, object]]:
    """Return policy-filtered retrieval results with citations."""
    lowered_query = query_text.lower()
    results: list[dict[str, object]] = []
    for item in corpus:
        dataset_id = str(item.get("dataset_id", ""))
        if dataset_id not in allowed_dataset_ids:
            continue
        text = str(item.get("text", ""))
        if lowered_query in text.lower():
            results.append(
                {
                    "artifact_id": item.get("artifact_id"),
                    "dataset_id": dataset_id,
                    "snippet": text[:180],
                    "citation": item.get("citation"),
                }
            )
    return results
