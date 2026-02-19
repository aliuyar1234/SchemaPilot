from __future__ import annotations

from pathlib import Path

from plugins.examples.google_drive_connector import discover as discover_google_drive
from plugins.examples.hubspot_export_connector import discover as discover_hubspot
from plugins.examples.imap_connector import discover as discover_imap
from plugins.examples.jira_connector import discover as discover_jira
from plugins.examples.sftp_connector import discover as discover_sftp
from plugins.examples.sharepoint_connector import discover as discover_sharepoint
from plugins.examples.smb_connector import discover as discover_smb
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


def test_sftp_reference_connector_discovers_csv_exports(tmp_path: Path) -> None:
    (tmp_path / "sftp_customers.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")
    rows = discover_sftp({"root_path": tmp_path.as_posix()})
    assert len(rows) == 1
    assert rows[0]["dataset_family"] == "sftp"


def test_google_drive_reference_connector_filters_by_prefix(tmp_path: Path) -> None:
    (tmp_path / "gdrive_invoices.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    (tmp_path / "other.csv").write_text("id,amount\n1,99\n", encoding="utf-8")
    rows = discover_google_drive({"root_path": tmp_path.as_posix()})
    assert len(rows) == 1
    assert rows[0]["dataset_family"] == "google_drive"


def test_imap_reference_connector_supports_cursor_incrementality(tmp_path: Path) -> None:
    first = tmp_path / "imap_mailbox_0001.eml"
    second = tmp_path / "imap_mailbox_0002.eml"
    first.write_text("From: a@example.com\nSubject: First\n\nBody", encoding="utf-8")
    second.write_text("From: b@example.com\nSubject: Second\n\nBody", encoding="utf-8")
    all_rows = discover_imap({"root_path": tmp_path.as_posix()})
    assert len(all_rows) == 2
    cursor_token = f"{float(first.stat().st_mtime):020.3f}:{first.as_posix()}"
    incremental_rows = discover_imap(
        {"root_path": tmp_path.as_posix(), "cursor_state": {"cursor": cursor_token}}
    )
    assert len(incremental_rows) <= 1
    if incremental_rows:
        assert incremental_rows[0]["path"].endswith("imap_mailbox_0002.eml")


def test_sharepoint_reference_connector_supports_delta_cursor(tmp_path: Path) -> None:
    first = tmp_path / "sp_invoice_001.csv"
    second = tmp_path / "sp_invoice_002.csv"
    first.write_text("id,amount\n1,10\n", encoding="utf-8")
    second.write_text("id,amount\n2,20\n", encoding="utf-8")
    all_rows = discover_sharepoint({"root_path": tmp_path.as_posix()})
    assert len(all_rows) == 2
    cursor = f"{float(first.stat().st_mtime):020.3f}:{first.as_posix()}"
    incremental_rows = discover_sharepoint(
        {"root_path": tmp_path.as_posix(), "cursor_state": {"delta_cursor": cursor}}
    )
    assert len(incremental_rows) <= 1
    if incremental_rows:
        assert incremental_rows[0]["path"].endswith("sp_invoice_002.csv")


def test_smb_reference_connector_discovers_files(tmp_path: Path) -> None:
    (tmp_path / "smb_customers.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")
    rows = discover_smb({"root_path": tmp_path.as_posix(), "include_globs": ["**/*.csv"]})
    assert len(rows) == 1
    assert rows[0]["dataset_family"] == "smb"


def test_jira_reference_connector_discovers_exports(tmp_path: Path) -> None:
    (tmp_path / "jira_issues.csv").write_text("id,summary\nSP-1,Investigate\n", encoding="utf-8")
    rows = discover_jira({"root_path": tmp_path.as_posix()})
    assert len(rows) == 1
    assert rows[0]["dataset_family"] == "jira"
