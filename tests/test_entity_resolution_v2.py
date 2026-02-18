from __future__ import annotations

from backend.workers.entity_resolution_v2 import (
    calibrate_er_threshold,
    resolve_entities_v2,
    rollback_er_v2,
)


def test_resolve_entities_v2_merges_probable_duplicates() -> None:
    records = [
        {"canonical_id": "c-1", "name": "Alice Johnson"},
        {"canonical_id": "c-2", "name": "Alice Jonson"},
        {"canonical_id": "c-3", "name": "Bob Stone"},
    ]

    def custom_similarity(left, right):  # type: ignore[no-untyped-def]
        l_name = str(left.get("name", "")).lower()
        r_name = str(right.get("name", "")).lower()
        if "alice" in l_name and "alice" in r_name:
            return 0.95
        return 0.0

    decisions = resolve_entities_v2(records, threshold=0.9, similarity_fn=custom_similarity)
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.member_ids == ["c-1", "c-2"]
    assert rollback_er_v2(decision) == ["c-1", "c-2"]


def test_calibrate_er_threshold_uses_labelled_scores() -> None:
    threshold = calibrate_er_threshold(
        [
            {"score": 0.91, "is_match": True},
            {"score": 0.88, "is_match": True},
            {"score": 0.4, "is_match": False},
        ]
    )
    assert 0.6 <= threshold <= 0.9
