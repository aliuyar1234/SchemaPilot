#!/usr/bin/env python3
"""Expanded fail-closed chaos drills executed as release-gate checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter


@dataclass
class DrillResult:
    id: str
    command: list[str]
    status: str
    duration_ms: float
    output_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="runtime/chaos_drills/report.json",
        help="JSON report path.",
    )
    return parser.parse_args()


def run_drills(*, root: Path, output_path: Path) -> dict[str, object]:
    output_dir = output_path.parent / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    drills = [
        (
            "CD-001",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_audit_fail_closed.py",
            ],
        ),
        (
            "CD-002",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_gateway_oidc_jwt_auth.py::test_gateway_oidc_jwt_denies_when_jwks_unavailable",
            ],
        ),
        (
            "CD-003",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_gateway_sql_safety.py::test_gateway_denies_query_that_exceeds_timeout_budget",
            ],
        ),
    ]
    results: list[DrillResult] = []
    for drill_id, command in drills:
        started = perf_counter()
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        duration_ms = round((perf_counter() - started) * 1000.0, 3)
        log_path = output_dir / f"{drill_id}.log"
        log_path.write_text(
            (completed.stdout or "") + ("\n" if completed.stdout else "") + (completed.stderr or ""),
            encoding="utf-8",
        )
        results.append(
            DrillResult(
                id=drill_id,
                command=command,
                status="pass" if completed.returncode == 0 else "fail",
                duration_ms=duration_ms,
                output_path=log_path.relative_to(root).as_posix(),
            )
        )
    payload = {
        "status": "pass" if all(item.status == "pass" for item in results) else "fail",
        "drills": [asdict(item) for item in results],
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    output_path = root / args.output
    payload = run_drills(root=root, output_path=output_path)
    print(output_path.relative_to(root).as_posix())
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

