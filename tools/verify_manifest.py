#!/usr/bin/env python3
"""Verify MANIFEST.sha256 against current files."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

IGNORED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "runtime",
}


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def verify_manifest(base: Path, manifest_path: Path) -> bool:
    """Verify manifest entries and report drift."""
    lines = [
        line.strip()
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ok = True
    for line in lines:
        expected_hash, rel = line.split("  ", 1)
        target = base / rel
        if _is_ignored(target):
            continue
        if not target.exists():
            print(f"FAIL {rel}: missing file")
            ok = False
            continue
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            print(f"FAIL {rel}: expected {expected_hash} got {actual_hash}")
            ok = False
    print("PASS" if ok else "FAIL")
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Root directory")
    parser.add_argument("--manifest", default="MANIFEST.sha256", help="Manifest path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    manifest = root / args.manifest
    if not manifest.exists():
        print(f"FAIL {args.manifest}: missing manifest")
        return 1
    return 0 if verify_manifest(root, manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
