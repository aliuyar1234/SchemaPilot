"""Qdrant retrieval adapter for gateway retrieval backend."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request as urlrequest


class QdrantUnavailableError(RuntimeError):
    """Raised when Qdrant retrieval backend is unreachable or invalid."""


def search_qdrant_documents(
    *,
    query_vector: list[float],
    workspace_id: str,
    allowed_dataset_ids: set[str],
    base_url: str,
    collection_name: str,
    timeout_ms: int = 3000,
    max_results: int = 20,
    request_fn: Callable[[str, dict[str, object], int], dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Search vector index in Qdrant and normalize retrieval rows."""
    if not query_vector or not allowed_dataset_ids:
        return []

    payload = {
        "vector": query_vector,
        "limit": max(1, min(max_results, 200)),
        "with_payload": True,
        "filter": {
            "must": [
                {"key": "workspace_id", "match": {"value": workspace_id}},
                {"key": "dataset_id", "match": {"any": sorted(allowed_dataset_ids)}},
            ]
        },
    }
    executor = request_fn or _request_search
    response = executor(
        _search_url(base_url=base_url, collection_name=collection_name), payload, timeout_ms
    )
    points = _extract_points(response)
    results: list[dict[str, object]] = []
    for point in points:
        payload_data = point.get("payload", {})
        if not isinstance(payload_data, dict):
            continue
        dataset_id = str(payload_data.get("dataset_id", "")).strip()
        artifact_id = str(payload_data.get("artifact_id", "")).strip()
        text = str(payload_data.get("text", ""))
        if dataset_id not in allowed_dataset_ids or not artifact_id:
            continue
        citation = str(payload_data.get("citation", f"artifact:{artifact_id}"))
        results.append(
            {
                "artifact_id": artifact_id,
                "dataset_id": dataset_id,
                "snippet": text[:180],
                "citation": citation,
            }
        )
    return results


def _search_url(*, base_url: str, collection_name: str) -> str:
    return f"{base_url.rstrip('/')}/collections/{collection_name.strip()}/points/search"


def _request_search(url: str, payload: dict[str, object], timeout_ms: int) -> dict[str, object]:
    timeout_seconds = max(timeout_ms, 1) / 1000.0
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    req = urlrequest.Request(  # nosec B310 - URL is controlled by operator config
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except (OSError, TimeoutError, urlerror.URLError) as exc:
        raise QdrantUnavailableError("qdrant_unavailable") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QdrantUnavailableError("qdrant_invalid_response") from exc
    if not isinstance(parsed, dict):
        raise QdrantUnavailableError("qdrant_invalid_response")
    return {str(key): value for key, value in parsed.items()}


def _extract_points(payload: dict[str, object]) -> list[dict[str, object]]:
    result = payload.get("result", [])
    if not isinstance(result, list):
        return []
    normalized: list[dict[str, object]] = []
    for row in result:
        if isinstance(row, dict):
            normalized.append({str(key): value for key, value in row.items()})
    return normalized

