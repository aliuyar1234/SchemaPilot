#!/usr/bin/env python3
"""Verify diagnostics bundles are redaction-safe and data-minimal."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from zipfile import ZipFile

FORBIDDEN_PATH_PREFIXES: tuple[str, ...] = (
    "artifacts/",
    "bronze/",
    "silver/",
    "gold/",
    "raw/",
)

FORBIDDEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)(password|passwd|api[_-]?key|secret|access[_-]?token)[\"']?\s*[:=]\s*[\"']?[^\s\"'<]+"
        ),
        "secret-like assignment",
    ),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "jwt-like token",
    ),
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "aws access key id",
    ),
    (
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "email-like pii",
    ),
)

MAX_MATCHES_PER_FILE = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to support bundle zip.")
    return parser.parse_args()


def verify_diag_bundle(path: str) -> list[str]:
    """Return deterministic violation list for a diagnostics bundle."""

    bundle_path = Path(path)
    if not bundle_path.exists():
        return [f"bundle_not_found: {bundle_path.as_posix()}"]
    if bundle_path.suffix.lower() != ".zip":
        return [f"bundle_not_zip: {bundle_path.as_posix()}"]

    violations: list[str] = []
    with ZipFile(bundle_path) as archive:
        for name in sorted(archive.namelist()):
            normalized = name.replace("\\", "/")
            if normalized.endswith("/"):
                continue
            lower_name = normalized.lower()
            for prefix in FORBIDDEN_PATH_PREFIXES:
                if lower_name.startswith(prefix):
                    violations.append(f"{normalized}: forbidden path prefix '{prefix}'")
            payload = archive.read(name)
            text = payload.decode("utf-8", errors="ignore")
            if not text:
                continue
            violations.extend(_scan_content(normalized, text))
    return sorted(set(violations))


def _scan_content(path: str, text: str) -> list[str]:
    findings: list[str] = []
    for pattern, reason in FORBIDDEN_PATTERNS:
        count = 0
        for match in pattern.finditer(text):
            snippet = match.group(0)
            if "<redacted>" in snippet.lower():
                continue
            findings.append(f"{path}: {reason}: {snippet[:80]}")
            count += 1
            if count >= MAX_MATCHES_PER_FILE:
                break
    return findings


def main() -> int:
    args = parse_args()
    violations = verify_diag_bundle(args.bundle)
    if violations:
        for violation in violations:
            print(f"FAIL {violation}")
        return 1
    print("PASS CHK-DIAG-BUNDLE-VERIFY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
