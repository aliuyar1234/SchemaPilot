#!/usr/bin/env python3
"""Run the PHASE_0 tooling baseline checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def maybe_run(cmd: list[str], cwd: Path | None = None) -> None:
    binary = cmd[0]
    resolved_binary = resolve_binary(binary)
    if resolved_binary is None:
        print(f"SKIP {' '.join(cmd)} (missing: {binary})")
        return
    run([resolved_binary, *cmd[1:]], cwd=cwd)


def resolve_binary(binary: str) -> str | None:
    """Resolve binary path with Windows npm.cmd fallback."""
    if binary == "npm" and sys.platform.startswith("win"):
        return shutil.which("npm.cmd")
    return shutil.which(binary)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    run([sys.executable, "-m", "ruff", "check", "backend", "cli", "tools", "tests"], cwd=root)
    run([sys.executable, "-m", "mypy", "backend", "cli", "tools"], cwd=root)
    # Fail on medium/high findings while still surfacing low-severity output in logs.
    run([sys.executable, "-m", "bandit", "-q", "-ll", "-r", "backend", "cli", "tools"], cwd=root)
    run([sys.executable, "tools/dependency_audit.py"], cwd=root)
    run([sys.executable, "tools/check_boundary_fitness.py"], cwd=root)
    run([sys.executable, "tools/check_no_bypass_ports.py"], cwd=root)
    run([sys.executable, "tools/check_openapi_compat.py"], cwd=root)
    run([sys.executable, "tools/generate_clients.py", "--check"], cwd=root)
    run([sys.executable, "tools/pack_lint.py"], cwd=root)
    run([sys.executable, "tools/policy_pack_test.py"], cwd=root)
    run([sys.executable, "tools/semantic_test.py"], cwd=root)
    run(
        [
            sys.executable,
            "tools/semantic_validate.py",
            "backend/shared_domain/semantic_manifest.example.json",
        ],
        cwd=root,
    )
    run([sys.executable, "-m", "pytest"], cwd=root)
    run([sys.executable, "tools/migration_check.py"], cwd=root)
    run([sys.executable, "tools/secrets_hygiene_check.py"], cwd=root)
    run([sys.executable, "tools/secrets_rotation_drill.py"], cwd=root)
    run([sys.executable, "tools/backup_restore_drill.py"], cwd=root)
    run([sys.executable, "tools/messybench_harness.py", "--regression"], cwd=root)
    run([sys.executable, "tools/e2e_golden_path.py", "--smoke"], cwd=root)
    run([sys.executable, "tools/ai_eval_harness.py", "--smoke"], cwd=root)
    run([sys.executable, "tools/perf_harness.py"], cwd=root)
    run([sys.executable, "tools/ssot_verify.py"], cwd=root)
    run([sys.executable, "tools/verify_manifest.py"], cwd=root)

    ui_dir = root / "ui"
    if (ui_dir / "package.json").exists():
        maybe_run(["npm", "ci"], cwd=ui_dir)
        maybe_run(["npm", "run", "lint"], cwd=ui_dir)
        maybe_run(["npm", "run", "typecheck"], cwd=ui_dir)
        maybe_run(["npm", "run", "test"], cwd=ui_dir)
        maybe_run(["npm", "audit", "--audit-level=high"], cwd=ui_dir)
    else:
        print("SKIP ui tooling (package.json missing)")

    print("PASS CHK-TOOLING-BASELINE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
