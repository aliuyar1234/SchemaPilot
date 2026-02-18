#!/usr/bin/env python3
"""Run documentation/link integrity checks relevant to this repository."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


CORE_FILES = {
    "README.md",
    "CONTRIBUTING.md",
    "docs/ARCHITECTURE.md",
    "LICENSE",
    "MANIFEST.sha256",
}

DOCS_DIRS = {"docs"}


@dataclass
class CheckResult:
    name: str
    ok: bool
    messages: list[str] = field(default_factory=list)


def read_markdown_files(root: Path) -> list[Path]:
    ignored_parts = {"node_modules", ".venv", ".git", "__pycache__"}
    return sorted(
        path
        for path in root.rglob("*.md")
        if path.is_file() and not any(part in ignored_parts for part in path.parts)
    )


def check_core_files(root: Path) -> CheckResult:
    missing = [item for item in sorted(CORE_FILES) if not (root / item).exists()]
    return CheckResult(name="CHK-CORE-FILES", ok=not missing, messages=missing)


def check_no_adhoc(root: Path) -> CheckResult:
    messages: list[str] = []
    for directory in sorted(DOCS_DIRS):
        target = root / directory
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if path.is_file() and path.suffix.lower() != ".md":
                messages.append(
                    f"Unexpected non-markdown in SSOT dir: {path.relative_to(root).as_posix()}"
                )
    return CheckResult(name="CHK-NO-ADHOC-FILES", ok=not messages, messages=messages)


def check_ref_integrity(root: Path) -> CheckResult:
    messages: list[str] = []
    for md_file in read_markdown_files(root):
        body = md_file.read_text(encoding="utf-8", errors="replace")
        for match in MD_LINK_RE.finditer(body):
            link = match.group(1)
            if "://" in link or link.startswith("#"):
                continue
            normalized = link.split("#", 1)[0]
            target = (md_file.parent / normalized).resolve()
            if root.resolve() not in target.parents and target != root.resolve():
                continue
            if not target.exists():
                messages.append(f"{md_file.relative_to(root).as_posix()}: broken link {link}")
    return CheckResult(name="CHK-REF-INTEGRITY", ok=not messages, messages=messages)


def run_checks(root: Path) -> list[CheckResult]:
    return [check_core_files(root), check_no_adhoc(root), check_ref_integrity(root)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    results = run_checks(root)
    failed = [result for result in results if not result.ok]

    for result in results:
        print(f"{result.name}: {'PASS' if result.ok else 'FAIL'}")
        for message in result.messages:
            print(f"- {message}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
