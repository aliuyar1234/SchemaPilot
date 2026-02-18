from __future__ import annotations

from backend.shared_domain.connector_state import (
    load_connector_state,
    next_cursor_from_discovery_rows,
    save_connector_state,
)


def test_connector_state_roundtrip(tmp_path) -> None:
    state_path = save_connector_state(
        storage_root=tmp_path.as_posix(),
        workspace_id="w1",
        source_id="s1",
        state={"cursor": "0001", "last_discovered_count": 2},
    )
    loaded = load_connector_state(
        storage_root=tmp_path.as_posix(),
        workspace_id="w1",
        source_id="s1",
    )
    assert state_path.endswith("connector_state/w1/s1/state.json")
    assert loaded["cursor"] == "0001"
    assert loaded["last_discovered_count"] == 2
    assert isinstance(loaded["updated_epoch"], int)


def test_next_cursor_from_discovery_rows_is_monotonic() -> None:
    rows = [
        {"path": "a.csv", "mtime_epoch": 10.0},
        {"path": "b.csv", "mtime_epoch": 20.0},
    ]
    first = next_cursor_from_discovery_rows(rows)
    second = next_cursor_from_discovery_rows(rows[:1], previous_cursor=first)
    assert second == first
