#!/usr/bin/env python3
"""Export SLO/SLA diagnostics (JSON or CSV) for a workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cli.schemapilot_cli.slo import export_slo_snapshot, render_slo_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Workspace identifier.")
    parser.add_argument(
        "--database-url",
        default="sqlite:///./runtime/schemapilot.db",
        help="Metadata database URL.",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=["json", "csv"],
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--role",
        default="platform_admin",
        help="Actor role for role-based SLO export controls.",
    )
    parser.add_argument(
        "--redacted",
        action="store_true",
        help="Export redacted aggregate-only payload for non-admin sharing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = export_slo_snapshot(
            database_url=args.database_url,
            workspace_id=args.workspace,
            actor_role=args.role,
            include_sensitive_breakdown=not bool(args.redacted),
        )
    except PermissionError:
        print("FAIL role_not_allowed_for_sensitive_slo_export")
        return 1
    rendered = (
        json.dumps(payload, indent=2, sort_keys=True)
        if args.format == "json"
        else render_slo_csv(payload).rstrip("\n")
    )
    output = str(args.output).strip()
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(f"PASS CHK-SLO-EXPORT: {path.as_posix()}")
        return 0
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
