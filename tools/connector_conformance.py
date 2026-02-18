#!/usr/bin/env python3
"""Connector certification harness for deterministic, strict discovery behavior."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.examples.google_drive_connector import discover as discover_google_drive
from plugins.examples.hubspot_export_connector import discover as discover_hubspot
from plugins.examples.imap_connector import discover as discover_imap
from plugins.examples.sftp_connector import discover as discover_sftp
from plugins.examples.zendesk_export_connector import discover as discover_zendesk

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


def certify_connector(*, connector_id: str, connector: ConnectorFn, scope: dict[str, object]) -> CertificationResult:
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
    scope = {"root_path": root_path}
    connectors: dict[str, ConnectorFn] = {
        "hubspot_export": discover_hubspot,
        "zendesk_export": discover_zendesk,
        "sftp": discover_sftp,
        "google_drive": discover_google_drive,
        "imap": discover_imap,
    }
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


def _create_fixture_exports(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "hubspot_contacts.csv": "id,email\n1,a@example.com\n",
        "zendesk_tickets.csv": "id,subject\n1,hello\n",
        "sftp_customers.csv": "id,name\n1,Alice\n",
        "gdrive_invoices.csv": "id,amount\n1,10\n",
        "imap_mailbox_0001.eml": "From: a@example.com\nSubject: Test\n\nBody",
    }
    for name, content in fixtures.items():
        (root / name).write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="runtime/conformance_exports", help="Connector export root.")
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
