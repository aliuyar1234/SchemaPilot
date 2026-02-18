"""Optional Qdrant indexing helpers for extracted documents."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request as urlrequest

from backend.shared_domain.embeddings_provider import EmbeddingsProvider, load_embeddings_provider
from backend.shared_domain.errors import DisabledIntegrationError
from backend.shared_domain.retrieval import load_retrieval_corpus


class QdrantIndexingError(RuntimeError):
    """Raised when Qdrant indexing is unavailable or misconfigured."""


def index_workspace_documents(
    *,
    workspace_id: str,
    storage_root: str,
    qdrant_url: str,
    collection_name: str,
    embeddings_provider_name: str = "disabled",
    embeddings_dimensions: int = 16,
    timeout_ms: int = 3000,
    embeddings_provider: EmbeddingsProvider | None = None,
    request_fn: Callable[[str, dict[str, object], int], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Load extracted corpus from storage and index into Qdrant."""
    corpus = load_retrieval_corpus(storage_root=storage_root, workspace_id=workspace_id)
    provider = embeddings_provider or load_embeddings_provider(
        provider_name=embeddings_provider_name,
        dimensions=embeddings_dimensions,
    )
    return index_documents_qdrant(
        workspace_id=workspace_id,
        corpus=corpus,
        qdrant_url=qdrant_url,
        collection_name=collection_name,
        timeout_ms=timeout_ms,
        embeddings_provider=provider,
        request_fn=request_fn,
    )


def index_documents_qdrant(
    *,
    workspace_id: str,
    corpus: list[dict[str, object]],
    qdrant_url: str,
    collection_name: str,
    embeddings_provider: EmbeddingsProvider,
    timeout_ms: int = 3000,
    request_fn: Callable[[str, dict[str, object], int], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Index corpus rows into Qdrant points API."""
    if not corpus:
        return {
            "workspace_id": workspace_id,
            "collection_name": collection_name,
            "indexed_count": 0,
            "status": "skipped_empty",
        }
    try:
        points = build_points_payload(
            workspace_id=workspace_id,
            corpus=corpus,
            embeddings_provider=embeddings_provider,
        )
    except DisabledIntegrationError as exc:
        raise QdrantIndexingError("embedding_provider_disabled") from exc
    executor = request_fn or _request_upsert
    response = executor(
        _points_url(base_url=qdrant_url, collection_name=collection_name),
        {"points": points},
        timeout_ms,
    )
    if str(response.get("status", "ok")).lower() not in {"ok", "accepted"}:
        raise QdrantIndexingError("qdrant_upsert_failed")
    return {
        "workspace_id": workspace_id,
        "collection_name": collection_name,
        "indexed_count": len(points),
        "status": "indexed",
    }


def build_points_payload(
    *,
    workspace_id: str,
    corpus: list[dict[str, object]],
    embeddings_provider: EmbeddingsProvider,
) -> list[dict[str, object]]:
    """Build deterministic Qdrant points payload."""
    points: list[dict[str, object]] = []
    for item in sorted(corpus, key=lambda row: str(row.get("artifact_id", ""))):
        artifact_id = str(item.get("artifact_id", "")).strip()
        dataset_id = str(item.get("dataset_id", "")).strip()
        text = str(item.get("text", ""))
        if not artifact_id or not dataset_id:
            continue
        citation = str(item.get("citation", f"artifact:{artifact_id}"))
        points.append(
            {
                "id": artifact_id,
                "vector": embeddings_provider.embed(text),
                "payload": {
                    "workspace_id": workspace_id,
                    "artifact_id": artifact_id,
                    "dataset_id": dataset_id,
                    "text": text,
                    "citation": citation,
                },
            }
        )
    return points


def _points_url(*, base_url: str, collection_name: str) -> str:
    return f"{base_url.rstrip('/')}/collections/{collection_name.strip()}/points?wait=true"


def _request_upsert(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
    timeout_seconds = max(timeout_ms, 1) / 1000.0
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    req = urlrequest.Request(  # nosec B310 - URL is controlled by operator config
        url,
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except (OSError, TimeoutError, urlerror.URLError) as exc:
        raise QdrantIndexingError("qdrant_unavailable") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QdrantIndexingError("qdrant_invalid_response") from exc
    if not isinstance(parsed, dict):
        raise QdrantIndexingError("qdrant_invalid_response")
    return {str(key): value for key, value in parsed.items()}

