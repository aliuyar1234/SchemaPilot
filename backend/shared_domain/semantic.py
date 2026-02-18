"""Semantic manifest schema normalization and validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

SEMANTIC_MANIFEST_VERSION = "1"
ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
JOIN_TYPES = {"inner", "left", "right", "full"}
AGGREGATIONS = {"sum", "count", "avg", "min", "max"}


def validate_semantic_manifest(
    manifest: Mapping[str, object],
    *,
    expected_workspace_id: str | None = None,
) -> dict[str, object]:
    """Validate and normalize semantic manifest payload."""
    version = str(manifest.get("manifest_version", "")).strip()
    if version != SEMANTIC_MANIFEST_VERSION:
        raise ValueError("invalid_manifest_version")
    workspace_id = str(manifest.get("workspace_id", "")).strip()
    if not workspace_id:
        raise ValueError("missing_workspace_id")
    if expected_workspace_id is not None and workspace_id != expected_workspace_id:
        raise ValueError("workspace_mismatch")

    entities_raw = manifest.get("entities", [])
    metrics_raw = manifest.get("metrics", [])
    joins_raw = manifest.get("joins", [])
    if not isinstance(entities_raw, list):
        raise ValueError("invalid_entities")
    if not isinstance(metrics_raw, list):
        raise ValueError("invalid_metrics")
    if not isinstance(joins_raw, list):
        raise ValueError("invalid_joins")

    entities = _normalize_entities(entities_raw)
    entity_ids = {str(row["entity_id"]) for row in entities}
    metrics = _normalize_metrics(metrics_raw, entity_ids=entity_ids)
    joins = _normalize_joins(joins_raw, entity_ids=entity_ids)
    return {
        "manifest_version": SEMANTIC_MANIFEST_VERSION,
        "workspace_id": workspace_id,
        "entities": entities,
        "metrics": metrics,
        "joins": joins,
    }


def semantic_manifest_checksum(manifest: Mapping[str, object]) -> str:
    """Return deterministic checksum for validated manifest."""
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_entities(rows: list[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("invalid_entity_row")
        entity_id = _normalized_id(row.get("entity_id"), field="entity_id")
        if entity_id in seen_ids:
            raise ValueError("duplicate_entity_id")
        seen_ids.add(entity_id)
        dataset_id = str(row.get("dataset_id", "")).strip()
        if not dataset_id:
            raise ValueError("missing_entity_dataset_id")
        primary_key = _normalized_id(row.get("primary_key"), field="primary_key")
        attributes_raw = row.get("attributes", [])
        if not isinstance(attributes_raw, list):
            raise ValueError("invalid_entity_attributes")
        attributes = sorted({_normalized_id(item, field="attribute") for item in attributes_raw})
        normalized.append(
            {
                "entity_id": entity_id,
                "dataset_id": dataset_id,
                "primary_key": primary_key,
                "attributes": attributes,
            }
        )
    return sorted(normalized, key=lambda item: str(item["entity_id"]))


def _normalize_metrics(rows: list[object], *, entity_ids: set[str]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("invalid_metric_row")
        metric_id = _normalized_id(row.get("metric_id"), field="metric_id")
        if metric_id in seen_ids:
            raise ValueError("duplicate_metric_id")
        seen_ids.add(metric_id)
        entity_id = _normalized_id(row.get("entity_id"), field="metric_entity_id")
        if entity_id not in entity_ids:
            raise ValueError("metric_entity_not_found")
        aggregation = str(row.get("aggregation", "")).strip().lower()
        if aggregation not in AGGREGATIONS:
            raise ValueError("invalid_metric_aggregation")
        field = _normalized_id(row.get("field"), field="metric_field")
        expression = str(row.get("expression", "")).strip()
        if not expression:
            expression = f"{aggregation}({field})"
        normalized.append(
            {
                "metric_id": metric_id,
                "entity_id": entity_id,
                "aggregation": aggregation,
                "field": field,
                "expression": expression,
            }
        )
    return sorted(normalized, key=lambda item: str(item["metric_id"]))


def _normalize_joins(rows: list[object], *, entity_ids: set[str]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("invalid_join_row")
        join_id = str(row.get("join_id", "")).strip()
        if not join_id:
            join_id = f"join_{index + 1}"
        join_id = _normalized_id(join_id, field="join_id")
        if join_id in seen_ids:
            raise ValueError("duplicate_join_id")
        seen_ids.add(join_id)
        left_entity_id = _normalized_id(row.get("left_entity_id"), field="left_entity_id")
        right_entity_id = _normalized_id(row.get("right_entity_id"), field="right_entity_id")
        if left_entity_id not in entity_ids or right_entity_id not in entity_ids:
            raise ValueError("join_entity_not_found")
        left_key = _normalized_id(row.get("left_key"), field="left_key")
        right_key = _normalized_id(row.get("right_key"), field="right_key")
        join_type = str(row.get("join_type", "inner")).strip().lower()
        if join_type not in JOIN_TYPES:
            raise ValueError("invalid_join_type")
        normalized.append(
            {
                "join_id": join_id,
                "left_entity_id": left_entity_id,
                "right_entity_id": right_entity_id,
                "left_key": left_key,
                "right_key": right_key,
                "join_type": join_type,
            }
        )
    return sorted(normalized, key=lambda item: str(item["join_id"]))


def _normalized_id(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing_{field}")
    if not ID_RE.match(text):
        raise ValueError(f"invalid_{field}")
    return text
