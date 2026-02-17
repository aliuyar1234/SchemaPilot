#!/usr/bin/env python3
"""Audit project dependencies declared in pyproject.toml."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


def collect_requirements(pyproject_path: Path) -> list[str]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    requirements: list[str] = list(project.get("dependencies", []))
    requirements.extend(project.get("optional-dependencies", {}).get("dev", []))
    return requirements


def write_requirements(path: Path, requirements: list[str]) -> None:
    unique_requirements = list(dict.fromkeys(requirements))
    path.write_text("".join(f"{item}\n" for item in unique_requirements), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    requirements = collect_requirements(root / "pyproject.toml")
    output_path = root / "runtime" / "dependency_audit_requirements.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_requirements(output_path, requirements)

    command = [sys.executable, "-m", "pip_audit", "--strict", "-r", output_path.as_posix()]
    print("$", " ".join(command))
    subprocess.run(command, cwd=root, check=True)
    print("PASS dependency audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
