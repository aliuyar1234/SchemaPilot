#!/usr/bin/env python3
"""Generate MANIFEST.sha256 in lexicographic order."""

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
    return any(part in IGNORED_PARTS or part.endswith(".egg-info") for part in path.parts)


def _stable_file_bytes(file_path: Path) -> bytes:
    """Return cross-platform stable bytes for hashing.

    Text files are normalized to LF line endings to avoid CRLF/LF drift
    across operating systems and git autocrlf settings.
    """
    raw = file_path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def generate_manifest(base: Path, output: Path) -> None:
    """Generate SHA256 manifest for all files except manifest itself."""
    files = sorted(p for p in base.rglob("*") if p.is_file() and not _is_ignored(p))
    lines: list[str] = []
    for file_path in files:
        rel = file_path.relative_to(base).as_posix()
        if rel == output.name:
            continue
        digest = hashlib.sha256(_stable_file_bytes(file_path)).hexdigest()
        lines.append(f"{digest}  {rel}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Root directory")
    parser.add_argument("--output", default="MANIFEST.sha256", help="Manifest output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = root / args.output
    generate_manifest(root, output)
    print(f"Generated {output.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
