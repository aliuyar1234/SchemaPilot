"""Semantic manifest drift detection helpers."""

from __future__ import annotations

from typing import Any


def detect_semantic_manifest_drift(
    *,
    semantic_manifest: dict[str, Any],
    available_columns_by_dataset: dict[str, set[str]],
) -> dict[str, object]:
    """Detect semantic references that are not present in current dataset schemas."""
    issues: list[dict[str, object]] = []
    entities_raw = semantic_manifest.get("entities", [])
    entities = entities_raw if isinstance(entities_raw, list) else []
    entity_to_dataset: dict[str, str] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("entity_id", "")).strip()
        dataset_id = str(entity.get("dataset_id", "")).strip()
        if entity_id and dataset_id:
            entity_to_dataset[entity_id] = dataset_id

    dimensions_raw = semantic_manifest.get("dimensions", [])
    dimensions = dimensions_raw if isinstance(dimensions_raw, list) else []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        dimension_id = str(dimension.get("dimension_id", "")).strip()
        entity_id = str(dimension.get("entity_id", "")).strip()
        dataset_id = entity_to_dataset.get(entity_id, "")
        if not dimension_id or not dataset_id:
            continue
        available = available_columns_by_dataset.get(dataset_id, set())
        if dimension_id not in available:
            issues.append(
                {
                    "issue_type": "missing_dimension_column",
                    "entity_id": entity_id,
                    "dataset_id": dataset_id,
                    "column": dimension_id,
                }
            )

    metrics_raw = semantic_manifest.get("metrics", [])
    metrics = metrics_raw if isinstance(metrics_raw, list) else []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_id = str(metric.get("metric_id", "")).strip()
        expression = str(metric.get("expression", "")).strip()
        entity_id = str(metric.get("entity_id", "")).strip()
        dataset_id = entity_to_dataset.get(entity_id, "")
        if not metric_id or not expression or not dataset_id:
            continue
        available = available_columns_by_dataset.get(dataset_id, set())
        for token in _expression_tokens(expression):
            if token in {"count", "sum", "avg", "min", "max"}:
                continue
            if token not in available:
                issues.append(
                    {
                        "issue_type": "missing_metric_expression_column",
                        "metric_id": metric_id,
                        "entity_id": entity_id,
                        "dataset_id": dataset_id,
                        "column": token,
                        "expression": expression,
                    }
                )
    return {
        "drift_detected": bool(issues),
        "issue_count": len(issues),
        "issues": issues,
    }


def _expression_tokens(expression: str) -> list[str]:
    normalized = expression.replace("(", " ").replace(")", " ").replace(",", " ")
    tokens = [part.strip().lower() for part in normalized.split() if part.strip()]
    return tokens
