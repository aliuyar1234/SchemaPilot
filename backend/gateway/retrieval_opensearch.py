"""OpenSearch retrieval adapter for gateway retrieval backend."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request as urlrequest


class OpenSearchUnavailableError(RuntimeError):
    """Raised when OpenSearch retrieval backend is unreachable or invalid."""


def search_opensearch_documents(
    *,
    query_text: str,
    workspace_id: str,
    allowed_dataset_ids: set[str],
    base_url: str,
    index_name: str,
    timeout_ms: int = 3000,
    max_results: int = 20,
    request_fn: Callable[[str, dict[str, object], int], dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Search documents in OpenSearch and return normalized retrieval rows."""
    if not query_text.strip() or not allowed_dataset_ids:
        return []

    payload = {
        "size": max(1, min(max_results, 200)),
        "_source": ["artifact_id", "dataset_id", "text", "citation"],
        "query": {
            "bool": {
                "must": [{"match": {"text": {"query": query_text}}}],
                "filter": [
                    {"term": {"workspace_id": workspace_id}},
                    {"terms": {"dataset_id": sorted(allowed_dataset_ids)}},
                ],
            }
        },
    }
    executor = request_fn or _request_search
    response = executor(_search_url(base_url=base_url, index_name=index_name), payload, timeout_ms)
    hits = _extract_hits(response)
    results: list[dict[str, object]] = []
    for hit in hits:
        source = hit.get("_source", {})
        if not isinstance(source, dict):
            continue
        dataset_id = str(source.get("dataset_id", "")).strip()
        artifact_id = str(source.get("artifact_id", "")).strip()
        text = str(source.get("text", ""))
        if dataset_id not in allowed_dataset_ids or not artifact_id:
            continue
        citation = str(source.get("citation", f"artifact:{artifact_id}"))
        results.append(
            {
                "artifact_id": artifact_id,
                "dataset_id": dataset_id,
                "snippet": text[:180],
                "citation": citation,
            }
        )
    return results


def _search_url(*, base_url: str, index_name: str) -> str:
    return f"{base_url.rstrip('/')}/{index_name.strip()}/_search"


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
        raise OpenSearchUnavailableError("opensearch_unavailable") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OpenSearchUnavailableError("opensearch_invalid_response") from exc
    if not isinstance(parsed, dict):
        raise OpenSearchUnavailableError("opensearch_invalid_response")
    return {str(key): value for key, value in parsed.items()}


def _extract_hits(payload: dict[str, object]) -> list[dict[str, object]]:
    hits_outer = payload.get("hits", {})
    if not isinstance(hits_outer, dict):
        return []
    hits = hits_outer.get("hits", [])
    if not isinstance(hits, list):
        return []
    normalized: list[dict[str, object]] = []
    for row in hits:
        if isinstance(row, dict):
            normalized.append({str(key): value for key, value in row.items()})
    return normalized
