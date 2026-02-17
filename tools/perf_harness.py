#!/usr/bin/env python3
"""Performance regression harness with baseline comparison."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from backend.control_plane.decision_engine import build_recommendation_report
from backend.gateway.executor import execute_sql


def _measure_ms(fn: Callable[[], object], repeats: int = 10) -> float:
    samples: list[float] = []
    for _ in range(repeats):
        started = perf_counter()
        fn()
        samples.append((perf_counter() - started) * 1000.0)
    samples.sort()
    percentile_index = int(round((len(samples) - 1) * 0.95))
    return round(samples[percentile_index], 3)


def _run_messybench(root: Path) -> float:
    started = perf_counter()
    result = subprocess.run(
        [sys.executable, "tools/messybench_harness.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return round((perf_counter() - started) * 1000.0, 3)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / "tools" / "perf_baseline.json").read_text(encoding="utf-8"))
    tolerance = float(baseline.get("tolerance_multiplier", 1.0))
    operations: dict[str, dict[str, float | bool]] = {}

    measured_gateway = _measure_ms(lambda: execute_sql("select 1 as one"), repeats=20)
    measured_decision = _measure_ms(
        lambda: build_recommendation_report(
            {
                "strict_security": False,
                "single_node_only": True,
                "prefer_low_ops": True,
            }
        ),
        repeats=20,
    )
    measured_messybench = _run_messybench(root)

    measured = {
        "gateway_execute_sql_ms": measured_gateway,
        "decision_engine_report_ms": measured_decision,
        "messybench_harness_ms": measured_messybench,
    }

    failures: list[str] = []
    for key, actual in measured.items():
        max_ms = float(baseline["operations"][key]["max_ms"])
        threshold = round(max_ms * tolerance, 3)
        passed = actual <= threshold
        operations[key] = {
            "actual_ms": actual,
            "threshold_ms": threshold,
            "pass": passed,
        }
        if not passed:
            failures.append(key)

    report = {
        "status": "pass" if not failures else "fail",
        "operations": operations,
    }
    report_dir = root / "runtime" / "perf"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "results.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if failures:
        print("FAIL CHK-PERF-HARNESS")
        for operation in failures:
            print("-", operation)
        print(report_path.relative_to(root).as_posix())
        return 1

    print("PASS CHK-PERF-HARNESS")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
