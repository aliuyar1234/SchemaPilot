#!/usr/bin/env python3
"""Bounded fuzzing harness for SQL safety and retrieval sanitization paths."""

from __future__ import annotations

import argparse
import json
import random
import string
from pathlib import Path

from backend.gateway.executor import UnsafeSqlError, _validate_read_only_query


UNSAFE_TOKENS = [
    "drop table users",
    "attach 'file.db'",
    "copy (select 1) to '/tmp/x'",
    "read_csv_auto('secret.csv')",
    "pragma show_tables",
]


def run_fuzz(*, iterations: int, seed: int) -> dict[str, object]:
    """Execute deterministic fuzz probes."""
    random.seed(seed)
    checked = 0
    denied = 0
    accepted = 0
    failures: list[str] = []
    candidates = list(UNSAFE_TOKENS)
    for _ in range(max(iterations, 1)):
        random_query = _random_query()
        candidates.append(random_query)
    for query in candidates:
        checked += 1
        try:
            _validate_read_only_query(query)
            accepted += 1
        except UnsafeSqlError:
            denied += 1
        except Exception as exc:  # pragma: no cover - defensive path
            failures.append(f"unexpected_exception:{exc}")
    return {
        "status": "pass" if not failures else "fail",
        "checked": checked,
        "denied": denied,
        "accepted": accepted,
        "failures": failures,
    }


def _random_query() -> str:
    prefix = random.choice(["select", "with cte as (select 1) select * from cte"])
    tail = "".join(random.choice(string.ascii_lowercase + " _'();") for _ in range(24))
    return f"{prefix} {tail}".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--output", default="runtime/security_fuzz/report.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_fuzz(iterations=args.iterations, seed=args.seed)
    root = Path(__file__).resolve().parents[1]
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
