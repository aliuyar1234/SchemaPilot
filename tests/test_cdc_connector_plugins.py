from __future__ import annotations

import json
from pathlib import Path

from plugins.examples.mysql_cdc_connector import discover as discover_mysql_cdc
from plugins.examples.postgres_cdc_connector import discover as discover_postgres_cdc


def test_postgres_cdc_connector_respects_lsn_cursor(tmp_path: Path) -> None:
    root = tmp_path / "cdc"
    root.mkdir(parents=True, exist_ok=True)
    events = [
        {"lsn": "0001", "relation": "invoice_events", "epoch": 1700000001},
        {"lsn": "0002", "relation": "invoice_events", "epoch": 1700000002},
    ]
    (root / "postgres_cdc_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in events) + "\n",
        encoding="utf-8",
    )
    first = discover_postgres_cdc({"root_path": root.as_posix()})
    second = discover_postgres_cdc(
        {"root_path": root.as_posix(), "cursor_state": {"lsn": "0001"}}
    )
    assert len(first) == 2
    assert len(second) == 1
    assert first[0]["dataset_family"] == "invoice_events"


def test_mysql_cdc_connector_respects_binlog_cursor(tmp_path: Path) -> None:
    root = tmp_path / "cdc"
    root.mkdir(parents=True, exist_ok=True)
    events = [
        {"binlog_pos": "0001", "table": "ticket_events", "epoch": 1700000101},
        {"binlog_pos": "0002", "table": "ticket_events", "epoch": 1700000102},
    ]
    (root / "mysql_cdc_events.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in events) + "\n",
        encoding="utf-8",
    )
    first = discover_mysql_cdc({"root_path": root.as_posix()})
    second = discover_mysql_cdc(
        {"root_path": root.as_posix(), "cursor_state": {"binlog_pos": "0001"}}
    )
    assert len(first) == 2
    assert len(second) == 1
    assert first[0]["dataset_family"] == "ticket_events"
