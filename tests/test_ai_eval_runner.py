from __future__ import annotations

import json
from pathlib import Path

from backend.ai_service.eval_runner import evaluate_regression_cases, load_regression_cases


def test_load_regression_cases_returns_sorted_case_list(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text(
        json.dumps({"case_id": "B", "path": "checks.ask_sql_status", "expected": 200}),
        encoding="utf-8",
    )
    (tmp_path / "a.json").write_text(
        json.dumps({"case_id": "A", "path": "checks.ask_sql_status", "expected": 200}),
        encoding="utf-8",
    )
    cases = load_regression_cases(tmp_path)
    assert [case["case_id"] for case in cases] == ["A", "B"]


def test_evaluate_regression_cases_reports_failures() -> None:
    report = {
        "checks": {"ask_sql_status": 200},
        "negative_checks": {"ask_sql_missing_citations_reason": "ai_citations_required"},
    }
    cases = [
        {
            "case_id": "PASS",
            "path": "checks.ask_sql_status",
            "op": "equals",
            "expected": 200,
        },
        {
            "case_id": "FAIL",
            "path": "negative_checks.ask_sql_missing_citations_reason",
            "op": "equals",
            "expected": "other",
        },
    ]
    result = evaluate_regression_cases(report=report, cases=cases)
    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["status"] == "fail"
