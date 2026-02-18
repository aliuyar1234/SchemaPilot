#!/usr/bin/env python3
"""Write weekly project KPI snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True, help="ISO week identifier (e.g. 2026-W08)")
    parser.add_argument("--ttfsa-minutes", required=True, type=float)
    parser.add_argument("--install-success-rate", required=True, type=float)
    parser.add_argument("--security-regressions", required=True, type=int)
    parser.add_argument("--deterministic-pass-rate", required=True, type=float)
    parser.add_argument("--active-contributors", required=True, type=int)
    parser.add_argument("--issue-response-hours", required=True, type=float)
    parser.add_argument("--output-root", default="runtime/kpi", help="KPI output folder")
    return parser.parse_args()


def validate_rate(name: str, value: float) -> float:
    if 0.0 <= value <= 1.0:
        return value
    raise ValueError(f"{name} must be between 0 and 1.")


def write_kpi_report(args: argparse.Namespace) -> Path:
    output_root = Path(args.output_root)
    weekly_dir = output_root / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "week": args.week,
        "recorded_at": datetime.now(tz=UTC).isoformat(),
        "kpis": {
            "time_to_first_safe_answer_minutes": max(args.ttfsa_minutes, 0.0),
            "install_success_rate": validate_rate(
                "install_success_rate",
                args.install_success_rate,
            ),
            "security_regression_count": max(args.security_regressions, 0),
            "deterministic_rebuild_pass_rate": validate_rate(
                "deterministic_pass_rate", args.deterministic_pass_rate
            ),
            "active_community_contributors": max(args.active_contributors, 0),
            "median_issue_response_hours": max(args.issue_response_hours, 0.0),
        },
    }
    weekly_path = weekly_dir / f"{args.week}.json"
    weekly_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (output_root / "latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return weekly_path


def main() -> int:
    args = parse_args()
    report_path = write_kpi_report(args)
    print(f"PASS KPI report generated: {report_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
