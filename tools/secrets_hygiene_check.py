#!/usr/bin/env python3
"""Secrets hygiene check for repository files."""

from __future__ import annotations

from pathlib import Path

from backend.shared_domain.secrets import contains_secret

IGNORED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
ALLOWLIST_PATHS = {
    "backend/shared_domain/secrets.py",
    "tools/secrets_hygiene_check.py",
    "checks/CHECKS_INDEX.md",
    "tests/test_observability.py",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in ALLOWLIST_PATHS:
            continue
        if any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if contains_secret(text):
            violations.append(rel)
    if violations:
        print("FAIL CHK-SECRETS-HYGIENE")
        for item in violations:
            print(f"- {item}")
        return 1
    print("PASS CHK-SECRETS-HYGIENE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
