#!/usr/bin/env python3
"""Run a systematic release gate and emit a machine-readable report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter


@dataclass
class StepResult:
    """Execution outcome for one release-gate step."""

    id: str
    description: str
    command: list[str]
    status: str
    duration_ms: float
    output_path: str


def run_step(
    *,
    root: Path,
    output_dir: Path,
    step_id: str,
    description: str,
    command: list[str],
    extra_env: dict[str, str] | None = None,
) -> StepResult:
    """Run one step and persist full command output."""
    output_path = output_dir / f"{step_id}.log"
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    started = perf_counter()
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    duration_ms = round((perf_counter() - started) * 1000.0, 3)
    output_path.write_text(
        (completed.stdout or "") + ("\n" if completed.stdout else "") + (completed.stderr or ""),
        encoding="utf-8",
    )
    return StepResult(
        id=step_id,
        description=description,
        command=command,
        status="pass" if completed.returncode == 0 else "fail",
        duration_ms=duration_ms,
        output_path=output_path.relative_to(root).as_posix(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="runtime/release_gate/report.json",
        help="Report output path (JSON).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    report_path = root / args.output
    output_dir = report_path.parent / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)

    enterprise_env = {
        "SCHEMAPILOT_PROFILE": "enterprise",
        "SCHEMAPILOT_BIND_ADDRESS": "127.0.0.1",
        "SCHEMAPILOT_AUTH_MODE": "local",
    }
    steps = [
        (
            "RG-001",
            "Doctor preflight",
            [sys.executable, "-m", "cli.schemapilot_cli.main", "doctor"],
            None,
        ),
        (
            "RG-002",
            "Full quality baseline",
            [sys.executable, "tools/check_tooling_baseline.py"],
            None,
        ),
        (
            "RG-003",
            "Enterprise-sim critical security suite",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_startup_security.py",
                "tests/test_non_bypass.py",
                "tests/test_gateway_policy.py",
                "tests/test_abac_masking.py",
                "tests/test_deletion_workflow.py",
            ],
            enterprise_env,
        ),
        (
            "RG-004",
            "Observability suite",
            [sys.executable, "-m", "pytest", "-q", "tests/test_observability.py"],
            None,
        ),
        (
            "RG-005",
            "Backup/restore drill",
            [sys.executable, "tools/backup_restore_drill.py"],
            None,
        ),
        (
            "RG-006",
            "Secrets rotation drill",
            [sys.executable, "tools/secrets_rotation_drill.py"],
            None,
        ),
        (
            "RG-007",
            "MessyBench harness",
            [sys.executable, "tools/messybench_harness.py", "--regression"],
            None,
        ),
        (
            "RG-007A",
            "Golden-path e2e smoke",
            [sys.executable, "tools/e2e_golden_path.py", "--smoke"],
            None,
        ),
        (
            "RG-007B",
            "AI eval harness smoke",
            [sys.executable, "tools/ai_eval_harness.py", "--smoke"],
            None,
        ),
        (
            "RG-008",
            "Performance harness",
            [sys.executable, "tools/perf_harness.py"],
            None,
        ),
        (
            "RG-009",
            "Manifest verification",
            [sys.executable, "tools/verify_manifest.py"],
            None,
        ),
        (
            "RG-010",
            "SSOT reference integrity",
            [sys.executable, "tools/ssot_verify.py"],
            None,
        ),
    ]

    results: list[StepResult] = []
    for step_id, description, command, env in steps:
        result = run_step(
            root=root,
            output_dir=output_dir,
            step_id=step_id,
            description=description,
            command=command,
            extra_env=env,
        )
        results.append(result)
        print(f"{result.id}: {result.status.upper()} ({result.duration_ms} ms)")
        if result.status == "fail":
            print(f"Failing step output: {result.output_path}")

    report = {
        "status": "go" if all(item.status == "pass" for item in results) else "no-go",
        "steps": [asdict(item) for item in results],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(report_path.relative_to(root).as_posix())
    return 0 if report["status"] == "go" else 1


if __name__ == "__main__":
    raise SystemExit(main())
