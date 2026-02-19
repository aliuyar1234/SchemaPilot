#!/usr/bin/env python3
"""Connector certification harness for deterministic, strict discovery behavior."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ConnectorFn = Callable[[dict[str, object]], list[dict[str, object]]]
REQUIRED_FIELDS = {"path", "dataset_family", "size_bytes", "mtime_epoch", "content_hash_sample"}


@dataclass(frozen=True)
class CertificationResult:
    """Certification result payload for one connector."""

    connector_id: str
    status: str
    errors: list[str]
    row_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "connector_id": self.connector_id,
            "status": self.status,
            "errors": list(self.errors),
            "row_count": self.row_count,
        }


def certify_connector(
    *, connector_id: str, connector: ConnectorFn, scope: dict[str, object]
) -> CertificationResult:
    """Run deterministic connector contract checks."""
    errors: list[str] = []
    first = _safe_discover(connector, scope=scope, errors=errors, stage="first_run")
    second = _safe_discover(connector, scope=scope, errors=errors, stage="second_run")
    if first != second:
        errors.append("non_deterministic_discovery_output")
    rows = first if isinstance(first, list) else []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_not_object:{index}")
            continue
        missing = sorted(REQUIRED_FIELDS.difference(row.keys()))
        if missing:
            errors.append(f"missing_fields:{index}:{','.join(missing)}")
        path = str(row.get("path", "")).strip()
        if not path:
            errors.append(f"empty_path:{index}")
    return CertificationResult(
        connector_id=connector_id,
        status="pass" if not errors else "fail",
        errors=errors,
        row_count=len(rows),
    )


def certify_default_connectors(*, root_path: str) -> list[CertificationResult]:
    """Certify bundled reference connectors against one export root."""
    scope: dict[str, object] = {"root_path": root_path}
    connectors = _load_reference_connectors()
    results: list[CertificationResult] = []
    for connector_id in sorted(connectors):
        results.append(
            certify_connector(
                connector_id=connector_id,
                connector=connectors[connector_id],
                scope=scope,
            )
        )
    return results


def _safe_discover(
    connector: ConnectorFn,
    *,
    scope: dict[str, object],
    errors: list[str],
    stage: str,
) -> list[dict[str, object]]:
    try:
        rows = connector(scope)
    except Exception as exc:  # pragma: no cover - exercised by caller tests
        errors.append(f"{stage}_exception:{exc}")
        return []
    if not isinstance(rows, list):
        errors.append(f"{stage}_invalid_output_type")
        return []
    normalized: list[dict[str, object]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append({str(key): value for key, value in row.items()})
    return sorted(
        normalized,
        key=lambda row: (
            str(row.get("path", "")),
            str(row.get("dataset_family", "")),
            str(row.get("mtime_epoch", "")),
        ),
    )


def _load_reference_connectors() -> dict[str, ConnectorFn]:
    """Load bundled connector entry points lazily to keep import ordering compliant."""
    connector_modules = {
        "hubspot_export": "plugins.examples.hubspot_export_connector",
        "zendesk_export": "plugins.examples.zendesk_export_connector",
        "jira": "plugins.examples.jira_connector",
        "sftp": "plugins.examples.sftp_connector",
        "smb": "plugins.examples.smb_connector",
        "google_drive": "plugins.examples.google_drive_connector",
        "sharepoint": "plugins.examples.sharepoint_connector",
        "imap": "plugins.examples.imap_connector",
        "postgres_cdc": "plugins.examples.postgres_cdc_connector",
        "mysql_cdc": "plugins.examples.mysql_cdc_connector",
    }
    connectors: dict[str, ConnectorFn] = {}
    for connector_id, module_name in connector_modules.items():
        module = importlib.import_module(module_name)
        discover = getattr(module, "discover", None)
        if not callable(discover):
            raise RuntimeError(f"connector module missing callable discover: {module_name}")
        connectors[connector_id] = discover
    return connectors


def _create_fixture_exports(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "hubspot_contacts.csv": "id,email\n1,a@example.com\n",
        "zendesk_tickets.csv": "id,subject\n1,hello\n",
        "jira_issues.csv": "id,summary\nSP-1,Investigate outage\n",
        "sftp_customers.csv": "id,name\n1,Alice\n",
        "smb_customers.csv": "id,name\n1,Alice\n",
        "gdrive_invoices.csv": "id,amount\n1,10\n",
        "sp_invoices.csv": "id,amount\n1,10\n",
        "imap_mailbox_0001.eml": "From: a@example.com\nSubject: Test\n\nBody",
        "postgres_cdc_events.jsonl": (
            '{"lsn":"00000001","relation":"invoice_events","epoch":1700000001}\n'
            '{"lsn":"00000002","relation":"invoice_events","epoch":1700000002}\n'
        ),
        "mysql_cdc_events.jsonl": (
            '{"binlog_pos":"00000001","table":"ticket_events","epoch":1700000010}\n'
            '{"binlog_pos":"00000002","table":"ticket_events","epoch":1700000011}\n'
        ),
    }
    for name, content in fixtures.items():
        (root / name).write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default="runtime/conformance_exports", help="Connector export root."
    )
    parser.add_argument(
        "--output",
        default="runtime/connector_conformance/report.json",
        help="Output report path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture_root = root / args.root
    _create_fixture_exports(fixture_root)
    results = certify_default_connectors(root_path=fixture_root.as_posix())
    report = {
        "status": "pass" if all(item.status == "pass" for item in results) else "fail",
        "results": [item.to_dict() for item in results],
    }
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    try:
        display = output_path.relative_to(root).as_posix()
    except ValueError:
        display = output_path.as_posix()
    print(display)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
