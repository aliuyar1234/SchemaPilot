"""AI output contract validation (fail-closed)."""

from __future__ import annotations

import re
from collections.abc import Mapping

_SQL_CITATION_PATTERN = re.compile(
    r"^sp://query/(?P<query_id>[^/]+)/dataset/(?P<dataset_id>[^/]+)/build/(?P<build_id>[^/]+)$"
)


def cannot_answer_safely_guidance() -> str:
    """Return the canonical fail-closed operator guidance."""

    return (
        "cannot_answer_safely: missing required gateway provenance/citations; "
        "verify entitlements and retry"
    )


def build_sql_answer_citations(*, provenance: Mapping[str, object]) -> list[dict[str, object]]:
    """Validate gateway SQL provenance and return normalized citation objects."""

    query_id = _require_non_empty_string(
        provenance.get("query_id"),
        field="query_id",
    )
    build_id = _require_non_empty_string(
        provenance.get("build_id"),
        field="build_id",
    )
    datasets_used = _require_non_empty_string_list(
        provenance.get("datasets_used"),
        field="datasets_used",
    )
    citations_raw = _require_non_empty_string_list(
        provenance.get("citations"),
        field="citations",
    )
    allowed_dataset_ids = _optional_string_list(provenance.get("allowed_dataset_ids"))
    evidence_bundle_refs = _optional_string_list(provenance.get("evidence_bundle_refs"))
    engine_type = _optional_non_empty_string(provenance.get("engine_type"))
    provenance_version = (
        _optional_non_empty_string(provenance.get("provenance_version")) or "1"
    )
    dataset_set = set(datasets_used)
    allowed_dataset_set = set(allowed_dataset_ids)
    citations: list[dict[str, object]] = []
    for citation_id in citations_raw:
        match = _SQL_CITATION_PATTERN.match(citation_id)
        if match is None:
            raise ValueError("ai_citation_invalid")
        citation_query_id = str(match.group("query_id"))
        citation_dataset_id = str(match.group("dataset_id"))
        citation_build_id = str(match.group("build_id"))
        if citation_query_id != query_id:
            raise ValueError("ai_citation_query_pointer_mismatch")
        if citation_build_id != build_id:
            raise ValueError("ai_citation_build_pointer_mismatch")
        if citation_dataset_id not in dataset_set:
            raise ValueError("ai_citation_dataset_not_authorized")
        if allowed_dataset_set and citation_dataset_id not in allowed_dataset_set:
            raise ValueError("ai_citation_dataset_not_authorized")
        citations.append(
            {
                "citation_id": citation_id,
                "dataset_id": citation_dataset_id,
                "build_id": build_id,
                "query_id": query_id,
                "source": "gateway.query",
                "provenance_version": provenance_version,
                "engine_type": engine_type,
                "evidence_bundle_refs": evidence_bundle_refs,
                "target_db_id": (
                    _optional_non_empty_string(provenance.get("target_db_id")) or None
                ),
                "target_schema_ref": (
                    _optional_non_empty_string(provenance.get("target_schema_ref")) or None
                ),
            }
        )
    return citations


def build_retrieval_answer_citations(
    *,
    provenance: Mapping[str, object],
    snippets: object,
) -> list[dict[str, object]]:
    """Validate gateway retrieval provenance and return normalized citation objects."""

    query_id = _require_non_empty_string(
        provenance.get("query_id"),
        field="query_id",
    )
    build_id = _require_non_empty_string(
        provenance.get("build_id"),
        field="build_id",
    )
    _ = _require_non_empty_string_list(
        provenance.get("datasets_used"),
        field="datasets_used",
    )
    citations_raw = _require_non_empty_string_list(
        provenance.get("citations"),
        field="citations",
    )
    allowed_dataset_ids = _optional_string_list(
        provenance.get("allowed_dataset_ids"),
    )
    evidence_bundle_refs = _optional_string_list(provenance.get("evidence_bundle_refs"))
    engine_type = _optional_non_empty_string(provenance.get("engine_type"))
    provenance_version = (
        _optional_non_empty_string(provenance.get("provenance_version")) or "1"
    )
    citation_to_dataset: dict[str, str] = {}
    if isinstance(snippets, list):
        for item in snippets:
            if not isinstance(item, dict):
                continue
            citation_id = _optional_non_empty_string(item.get("citation"))
            dataset_id = _optional_non_empty_string(item.get("dataset_id"))
            if citation_id and dataset_id:
                citation_to_dataset[citation_id] = dataset_id
    citations: list[dict[str, object]] = []
    allowed_set = set(allowed_dataset_ids)
    for citation_id in citations_raw:
        dataset_id = citation_to_dataset.get(citation_id, "")
        if not dataset_id:
            raise ValueError("ai_citation_missing_dataset_pointer")
        if allowed_set and dataset_id not in allowed_set:
            raise ValueError("ai_citation_dataset_not_authorized")
        citations.append(
            {
                "citation_id": citation_id,
                "dataset_id": dataset_id,
                "build_id": build_id,
                "query_id": query_id,
                "source": "gateway.retrieve",
                "provenance_version": provenance_version,
                "engine_type": engine_type,
                "evidence_bundle_refs": evidence_bundle_refs,
            }
        )
    return citations


def _require_non_empty_string(value: object, *, field: str) -> str:
    normalized = _optional_non_empty_string(value)
    if normalized is None:
        raise ValueError(f"ai_provenance_required:{field}")
    return normalized


def _optional_non_empty_string(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _require_non_empty_string_list(value: object, *, field: str) -> list[str]:
    normalized = _optional_string_list(value)
    if not normalized:
        if field == "citations":
            raise ValueError("ai_citations_required")
        raise ValueError(f"ai_provenance_required:{field}")
    return normalized


def _optional_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})
