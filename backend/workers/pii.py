"""PII proposal heuristics with confidence + evidence output."""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\-\s]{6,}$")
IBAN_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")


def detect_pii_proposals(column_name: str, values: list[str]) -> dict[str, object]:
    """Return PII proposal with confidence and evidence bundle."""
    sanitized = [value.strip() for value in values if value.strip()]
    total = len(sanitized)
    if total == 0:
        return {
            "column_name": column_name,
            "tag": "unknown",
            "confidence": 0.0,
            "evidence": {"matches": {}, "samples_redacted": []},
            "review_required": True,
        }

    matches = {
        "email": sum(1 for value in sanitized if EMAIL_RE.match(value)),
        "phone": sum(1 for value in sanitized if PHONE_RE.match(value)),
        "iban": sum(1 for value in sanitized if IBAN_RE.match(value)),
    }
    top_tag, top_count = max(matches.items(), key=lambda item: item[1])
    confidence = top_count / total
    redacted_samples = [_redact(value) for value in sanitized[:5]]
    return {
        "column_name": column_name,
        "tag": top_tag if top_count > 0 else "none",
        "confidence": round(confidence, 4),
        "evidence": {"matches": matches, "samples_redacted": redacted_samples},
        "review_required": confidence < 0.95,
    }


def _redact(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[:1] + ("*" * (len(value) - 2)) + value[-1:]
