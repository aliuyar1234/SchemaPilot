"""Shared retrieval filtering helpers."""

from __future__ import annotations

import json
from pathlib import Path


def load_retrieval_corpus(*, storage_root: str, workspace_id: str) -> list[dict[str, object]]:
    """Load retrieval corpus from server-side extracted document artifacts."""
    root = Path(storage_root) / "documents" / workspace_id
    if not root.exists():
        return []
    corpus: list[dict[str, object]] = []
    for evidence_path in sorted(root.glob("**/extracted/evidence.json")):
        text_path = evidence_path.with_name("text.json")
        if not text_path.exists():
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            extracted = json.loads(text_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        dataset_id = str(evidence.get("dataset_id", ""))
        artifact_id = str(evidence.get("artifact_id", ""))
        text = str(extracted.get("text", ""))
        if not dataset_id or not artifact_id:
            continue
        citation = str(evidence.get("citation", f"artifact:{artifact_id}"))
        corpus.append(
            {
                "artifact_id": artifact_id,
                "dataset_id": dataset_id,
                "text": text,
                "citation": citation,
            }
        )
    return corpus


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
