#!/usr/bin/env python3
"""Simulate a clean-room install and validate bootstrap commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, check=False, capture_output=True, text=True)


def _python_in_venv(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs_dir = root / "runtime" / "cleanroom"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="schemapilot_cleanroom_") as temp_dir:
        venv_dir = Path(temp_dir) / ".venv"
        started = perf_counter()
        create_venv = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        (logs_dir / "create_venv.log").write_text(
            (create_venv.stdout or "") + "\n" + (create_venv.stderr or ""),
            encoding="utf-8",
        )
        if create_venv.returncode != 0:
            print("FAIL clean-room venv creation")
            return 1

        python_bin = _python_in_venv(venv_dir)
        env = os.environ.copy()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

        install = _run([str(python_bin), "-m", "pip", "install", "-e", ".[dev]"], cwd=root, env=env)
        (logs_dir / "install.log").write_text(
            (install.stdout or "") + "\n" + (install.stderr or ""),
            encoding="utf-8",
        )
        if install.returncode != 0:
            print("FAIL clean-room dependency install")
            return 1

        doctor = _run(
            [str(python_bin), "-m", "cli.schemapilot_cli.main", "doctor"],
            cwd=root,
            env=env,
        )
        (logs_dir / "doctor.log").write_text(
            (doctor.stdout or "") + "\n" + (doctor.stderr or ""),
            encoding="utf-8",
        )
        if doctor.returncode != 0:
            print("FAIL clean-room doctor")
            return 1

        smoke = _run([str(python_bin), "tools/smoke_test.py"], cwd=root, env=env)
        (logs_dir / "smoke.log").write_text(
            (smoke.stdout or "") + "\n" + (smoke.stderr or ""),
            encoding="utf-8",
        )
        if smoke.returncode != 0:
            print("FAIL clean-room smoke")
            return 1

        elapsed = round((perf_counter() - started) * 1000.0, 3)
        (logs_dir / "summary.txt").write_text(
            f"PASS clean-room install check ({elapsed} ms)\n",
            encoding="utf-8",
        )
        print("PASS clean-room install check")
        print((logs_dir / "summary.txt").relative_to(root).as_posix())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
