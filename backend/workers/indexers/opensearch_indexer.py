"""Optional OpenSearch indexing helpers for extracted documents."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error as urlerror
from urllib import request as urlrequest

from backend.shared_domain.retrieval import load_retrieval_corpus


class OpenSearchIndexingError(RuntimeError):
    """Raised when OpenSearch indexing is unavailable or returns invalid output."""


def index_workspace_documents(
    *,
    workspace_id: str,
    storage_root: str,
    opensearch_url: str,
    index_name: str,
    timeout_ms: int = 3000,
    request_fn: Callable[[str, bytes, int], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Load extracted corpus from storage and index into OpenSearch."""
    corpus = load_retrieval_corpus(storage_root=storage_root, workspace_id=workspace_id)
    return index_documents_opensearch(
        workspace_id=workspace_id,
        corpus=corpus,
        opensearch_url=opensearch_url,
        index_name=index_name,
        timeout_ms=timeout_ms,
        request_fn=request_fn,
    )


def index_documents_opensearch(
    *,
    workspace_id: str,
    corpus: list[dict[str, object]],
    opensearch_url: str,
    index_name: str,
    timeout_ms: int = 3000,
    request_fn: Callable[[str, bytes, int], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Index corpus rows into OpenSearch bulk API."""
    if not corpus:
        return {
            "workspace_id": workspace_id,
            "index_name": index_name,
            "indexed_count": 0,
            "status": "skipped_empty",
        }
    payload = build_bulk_payload(
        workspace_id=workspace_id,
        corpus=corpus,
        index_name=index_name,
    )
    executor = request_fn or _request_bulk
    response = executor(_bulk_url(base_url=opensearch_url), payload, timeout_ms)
    if bool(response.get("errors", False)):
        raise OpenSearchIndexingError("opensearch_bulk_errors")
    return {
        "workspace_id": workspace_id,
        "index_name": index_name,
        "indexed_count": len(corpus),
        "status": "indexed",
    }


def build_bulk_payload(
    *,
    workspace_id: str,
    corpus: list[dict[str, object]],
    index_name: str,
) -> bytes:
    """Build deterministic OpenSearch bulk NDJSON payload."""
    lines: list[str] = []
    for item in sorted(corpus, key=lambda row: str(row.get("artifact_id", ""))):
        artifact_id = str(item.get("artifact_id", "")).strip()
        dataset_id = str(item.get("dataset_id", "")).strip()
        if not artifact_id or not dataset_id:
            continue
        doc = {
            "workspace_id": workspace_id,
            "artifact_id": artifact_id,
            "dataset_id": dataset_id,
            "text": str(item.get("text", "")),
            "citation": str(item.get("citation", f"artifact:{artifact_id}")),
        }
        lines.append(json.dumps({"index": {"_index": index_name}}, sort_keys=True))
        lines.append(json.dumps(doc, sort_keys=True))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _bulk_url(*, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/_bulk"


def _request_bulk(url: str, payload: bytes, timeout_ms: int) -> dict[str, object]:
    timeout_seconds = max(timeout_ms, 1) / 1000.0
    req = urlrequest.Request(  # nosec B310 - URL is controlled by operator config
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-ndjson",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except (OSError, TimeoutError, urlerror.URLError) as exc:
        raise OpenSearchIndexingError("opensearch_unavailable") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OpenSearchIndexingError("opensearch_invalid_response") from exc
    if not isinstance(parsed, dict):
        raise OpenSearchIndexingError("opensearch_invalid_response")
    return {str(key): value for key, value in parsed.items()}
