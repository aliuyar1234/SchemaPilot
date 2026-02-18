from __future__ import annotations

from pathlib import Path

from plugins.examples.hubspot_export_connector import discover as discover_hubspot
from plugins.examples.zendesk_export_connector import discover as discover_zendesk


def test_hubspot_reference_connector_discovers_exports(tmp_path: Path) -> None:
    (tmp_path / "hubspot_contacts.csv").write_text("id,email\n1,a@example.com\n", encoding="utf-8")
    (tmp_path / "hubspot_deals.csv").write_text("id,amount\n10,100\n", encoding="utf-8")
    rows = discover_hubspot({"root_path": tmp_path.as_posix()})
    assert len(rows) == 2
    assert {row["dataset_family"] for row in rows} == {"hubspot"}


def test_zendesk_reference_connector_requires_existing_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    try:
        discover_zendesk({"root_path": missing.as_posix()})
    except ValueError as exc:
        assert str(exc) == "root_path_not_found"
    else:  # pragma: no cover
        raise AssertionError("expected root_path_not_found")
