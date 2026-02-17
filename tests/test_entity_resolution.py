from __future__ import annotations

from backend.workers.entity_resolution import resolve_entities, rollback_merge


def test_entity_resolution_is_reversible() -> None:
    records = [
        {"canonical_id": "sid_1", "name": "Alice Smith"},
        {"canonical_id": "sid_2", "name": "alice-smith"},
        {"canonical_id": "sid_3", "name": "Bob Jones"},
    ]
    decisions = resolve_entities(records)
    assert len(decisions) == 1
    restored = rollback_merge(decisions[0])
    assert restored == ["sid_1", "sid_2"]
