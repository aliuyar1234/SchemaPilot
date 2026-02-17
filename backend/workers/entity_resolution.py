"""Deterministic entity resolution baseline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MergeDecision:
    """Reversible ER merge decision."""

    cluster_id: str
    canonical_id: str
    member_ids: list[str]
    confidence: float
    reversible_payload: dict[str, object]


def resolve_entities(
    records: list[dict[str, object]],
    *,
    canonical_id_field: str = "canonical_id",
    name_field: str = "name",
) -> list[MergeDecision]:
    """Resolve potential duplicates using deterministic normalized name matching."""
    buckets: dict[str, list[dict[str, object]]] = {}
    for record in records:
        key = _normalize_name(str(record.get(name_field, "")))
        if not key:
            continue
        buckets.setdefault(key, []).append(record)

    decisions: list[MergeDecision] = []
    for key, members in sorted(buckets.items(), key=lambda item: item[0]):
        if len(members) < 2:
            continue
        sorted_members = sorted(members, key=lambda item: str(item.get(canonical_id_field, "")))
        canonical_id = str(sorted_members[0].get(canonical_id_field))
        member_ids = [str(item.get(canonical_id_field, "")) for item in sorted_members]
        decisions.append(
            MergeDecision(
                cluster_id=f"cluster_{key}",
                canonical_id=canonical_id,
                member_ids=member_ids,
                confidence=1.0,
                reversible_payload={"pre_merge_member_ids": member_ids},
            )
        )
    return decisions


def rollback_merge(decision: MergeDecision) -> list[str]:
    """Return original member IDs for reversible rollback."""
    payload = decision.reversible_payload
    pre_merge = payload.get("pre_merge_member_ids", [])
    return [str(value) for value in pre_merge] if isinstance(pre_merge, list) else []


def _normalize_name(name: str) -> str:
    return "".join(ch for ch in name.lower().strip() if ch.isalnum())
