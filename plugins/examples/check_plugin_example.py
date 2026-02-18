"""Example quality check plugin contract for SchemaPilot."""

from __future__ import annotations


def check_id() -> str:
    return "example.check.row_budget"


def run_check() -> dict[str, object]:
    return {
        "status": "pass",
        "details": {
            "message": "Example check passed.",
            "checked_targets": ["bronze/demo_dataset"],
        },
    }
