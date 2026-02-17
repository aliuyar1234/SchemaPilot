"""Secrets hygiene utilities."""

from __future__ import annotations

import json
import re
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)password\s*=\s*[^,\s]+"),
]


def redact_secrets(text: str) -> str:
    """Redact known secret-like values in log messages."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def contains_secret(text: str) -> bool:
    """Detect whether text contains known secret-like values."""
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def rotate_secret_reference(
    *, config_path: Path, key: str, new_reference: str
) -> tuple[str | None, str]:
    """Rotate a credentials reference in a JSON config file."""
    config = config_path.read_text(encoding="utf-8")
    if contains_secret(new_reference):
        raise ValueError("new_reference_looks_like_secret")
    payload = json.loads(config)
    previous = payload.get(key)
    payload[key] = new_reference
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return (str(previous) if previous is not None else None, new_reference)
