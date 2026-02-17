from __future__ import annotations

from backend.workers.contracts import evaluate_quality_contracts


def test_quality_contracts_quarantine_failures() -> None:
    rows = [
        {"id": "1", "email": "a@example.com"},
        {"id": "1", "email": ""},
        {"id": "2"},
    ]
    result = evaluate_quality_contracts(
        rows,
        required_columns=["id", "email"],
        not_null_columns=["email"],
        unique_columns=["id"],
    )
    assert len(result.passed_rows) == 1
    assert len(result.quarantined_rows) == 2
    assert len(result.failures) == 2
