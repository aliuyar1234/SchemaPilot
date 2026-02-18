#!/usr/bin/env python3
"""Generate deterministic build provenance metadata for release artifacts."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runtime/supply_chain/provenance.json")
    return parser.parse_args()


def _git_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def build_provenance(*, root: Path) -> dict[str, object]:
    return {
        "build_epoch_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(root),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "ci": {
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_ref": os.getenv("GITHUB_REF"),
            "github_sha": os.getenv("GITHUB_SHA"),
        },
    }


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_provenance(root=root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        display = output_path.relative_to(root).as_posix()
    except ValueError:
        display = output_path.as_posix()
    print(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
