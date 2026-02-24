#!/usr/bin/env python3
"""Run SSOT integrity checks relevant to this repository."""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

EVIDENCE_RE = re.compile(r"evidence:\s*([A-Za-z0-9_./-]+)\s*::\s*([^\n]+)")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


CORE_FILES = {
    "README.md",
    "AGENTS.md",
    "CONSTITUTION.md",
    "DECISIONS.md",
    "ASSUMPTIONS.md",
    "PROGRESS.md",
    "CHANGELOG.md",
    "AUDIT_REPORT.md",
    "MANIFEST.sha256",
    "checks/CHECKS_INDEX.md",
    "templates/SESSION_PROTOCOL.md",
    "templates/PR_REVIEW_CHECKLIST.md",
    "spec/00_PROJECT_FINGERPRINT.md",
    "spec/01_SCOPE.md",
    "spec/10_PHASES_AND_TASKS.md",
    "spec/11_QUALITY_GATES.md",
}

SSOT_DIRS = {"spec", "checks", "templates"}

OPTIONAL_INTERNAL_GLOBS = {
    "AGENTS.md",
    "ASSUMPTIONS.md",
    "AUDIT_REPORT.md",
    "CHANGELOG.md",
    "CONSTITUTION.md",
    "DECISIONS.md",
    "PROGRESS.md",
    "TASKLIST.md",
    "TASKLIST_NEXT.md",
    "TASKLIST_NEXT_V2.md",
    "ENTERPRISE_RELEASE_CHECKLIST.md",
    "checks/QUESTIONS_FOR_USER.md",
    "docs/GPT_PRO*.md",
}


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


def _is_optional_internal_path(rel_path: str) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in OPTIONAL_INTERNAL_GLOBS)


def check_core_files(root: Path) -> CheckResult:
    missing = [
        item
        for item in sorted(CORE_FILES)
        if not (root / item).exists() and not _is_optional_internal_path(item)
    ]
    return CheckResult(name="CHK-CORE-FILES", ok=not missing, messages=missing)


def check_no_adhoc(root: Path) -> CheckResult:
    messages: list[str] = []
    for directory in sorted(SSOT_DIRS):
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
        for match in EVIDENCE_RE.finditer(body):
            rel_path = match.group(1).strip()
            phrase = match.group(2).strip().rstrip("|").strip()
            target = root / rel_path
            if not target.exists():
                if _is_optional_internal_path(rel_path):
                    continue
                messages.append(
                    f"{md_file.relative_to(root).as_posix()}: missing evidence file {rel_path}"
                )
                continue
            target_body = target.read_text(encoding="utf-8", errors="replace")
            if phrase not in target_body:
                file_name = md_file.relative_to(root).as_posix()
                message = f"{file_name}: phrase not found in {rel_path} :: {phrase}"
                messages.append(message)

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
