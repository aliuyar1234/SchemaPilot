"""Opt-in probabilistic entity resolution with rollback metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ErV2Decision:
    """Probabilistic merge decision with rollback metadata."""

    cluster_id: str
    canonical_id: str
    member_ids: list[str]
    score: float
    threshold: float
    rollback_payload: dict[str, object]


SimilarityFn = Callable[[dict[str, object], dict[str, object]], float]


def resolve_entities_v2(
    records: list[dict[str, object]],
    *,
    id_field: str = "canonical_id",
    name_field: str = "name",
    threshold: float = 0.85,
    similarity_fn: SimilarityFn | None = None,
) -> list[ErV2Decision]:
    """Resolve entities using pairwise probabilistic similarity."""
    scorer = similarity_fn or _default_similarity
    decisions: list[ErV2Decision] = []
    used_ids: set[str] = set()
    normalized_threshold = max(0.0, min(1.0, threshold))
    sorted_records = sorted(records, key=lambda row: str(row.get(id_field, "")))
    for index, left in enumerate(sorted_records):
        left_id = str(left.get(id_field, "")).strip()
        if not left_id or left_id in used_ids:
            continue
        members = [left_id]
        best_score = 1.0
        for right in sorted_records[index + 1 :]:
            right_id = str(right.get(id_field, "")).strip()
            if not right_id or right_id in used_ids:
                continue
            score = scorer(left, right)
            if score >= normalized_threshold:
                members.append(right_id)
                best_score = min(best_score, score)
        if len(members) < 2:
            continue
        members_sorted = sorted(set(members))
        for member_id in members_sorted:
            used_ids.add(member_id)
        canonical = members_sorted[0]
        cluster_key = _normalize_token(str(left.get(name_field, ""))) or canonical
        decisions.append(
            ErV2Decision(
                cluster_id=f"erv2_{cluster_key}",
                canonical_id=canonical,
                member_ids=members_sorted,
                score=best_score,
                threshold=normalized_threshold,
                rollback_payload={"pre_merge_member_ids": members_sorted},
            )
        )
    return decisions


def calibrate_er_threshold(validation_pairs: list[dict[str, object]]) -> float:
    """Calibrate threshold from labeled validation pairs."""
    positives: list[float] = []
    negatives: list[float] = []
    for row in validation_pairs:
        if not isinstance(row, dict):
            continue
        score = _as_float(row.get("score"), default=0.0)
        is_match = bool(row.get("is_match", False))
        if is_match:
            positives.append(score)
        else:
            negatives.append(score)
    if not positives:
        return 0.9
    positive_floor = min(positives)
    negative_ceiling = max(negatives) if negatives else 0.0
    threshold = (positive_floor + negative_ceiling) / 2.0
    return max(0.5, min(0.99, threshold))


def rollback_er_v2(decision: ErV2Decision) -> list[str]:
    """Return original IDs for a merge decision."""
    members = decision.rollback_payload.get("pre_merge_member_ids", [])
    if not isinstance(members, list):
        return []
    return [str(item) for item in members if str(item).strip()]


def _default_similarity(left: dict[str, object], right: dict[str, object]) -> float:
    left_tokens = _tokenize(_normalize_token(str(left.get("name", ""))))
    right_tokens = _tokenize(_normalize_token(str(right.get("name", ""))))
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(intersection) / len(union)


def _normalize_token(value: str) -> str:
    return "".join(ch if ch.isalnum() else " " for ch in value.lower().strip())


def _tokenize(value: str) -> set[str]:
    return {part for part in value.split() if part}


def _as_float(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default
