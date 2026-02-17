"""Inference helpers for schema, key, and relationship proposals."""

from __future__ import annotations

from collections import defaultdict
from typing import cast


def cluster_dataset_families(dataset_names: list[str]) -> dict[str, list[str]]:
    """Cluster datasets by inferred family prefix."""
    clusters: dict[str, list[str]] = defaultdict(list)
    for name in sorted(dataset_names):
        family = _family_from_name(name)
        clusters[family].append(name)
    return dict(clusters)


def infer_primary_key_candidates(
    rows: list[dict[str, object]], columns: list[str]
) -> list[dict[str, object]]:
    """Infer PK candidates from uniqueness/null signals."""
    proposals: list[dict[str, float | str]] = []
    row_count = len(rows)
    for column in columns:
        values = [row.get(column) for row in rows]
        null_count = sum(1 for value in values if value in (None, ""))
        unique_count = len(set(values))
        uniqueness = unique_count / row_count if row_count else 0.0
        confidence = max(0.0, uniqueness - (null_count / row_count if row_count else 0.0))
        proposals.append(
            {
                "column": column,
                "confidence": round(confidence, 4),
                "null_rate": round((null_count / row_count if row_count else 0.0), 4),
            }
        )
    return sorted(
        cast(list[dict[str, object]], proposals),
        key=lambda item: cast(float, item["confidence"]),
        reverse=True,
    )


def infer_relationship_candidates(
    left_rows: list[dict[str, object]],
    right_rows: list[dict[str, object]],
    left_column: str,
    right_column: str,
) -> dict[str, object]:
    """Infer FK relationship via overlap heuristics."""
    left_values = {
        row.get(left_column) for row in left_rows if row.get(left_column) not in (None, "")
    }
    right_values = {
        row.get(right_column) for row in right_rows if row.get(right_column) not in (None, "")
    }
    overlap = left_values & right_values
    denominator = len(left_values) if left_values else 1
    confidence = len(overlap) / denominator
    return {
        "left_column": left_column,
        "right_column": right_column,
        "overlap_count": len(overlap),
        "left_unique_count": len(left_values),
        "confidence": round(confidence, 4),
        "missing_evidence": [] if left_values else ["left_column_no_values"],
    }


def _family_from_name(name: str) -> str:
    token = name.lower().split(".")[0]
    for separator in ("_", "-", " "):
        if separator in token:
            return token.split(separator)[0]
    return token
