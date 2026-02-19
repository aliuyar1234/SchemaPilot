"""Deterministic AI regression-case loader and evaluator."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path


def load_regression_cases(cases_root: Path) -> list[dict[str, object]]:
    """Load JSON regression cases from one directory in deterministic order."""
    if not cases_root.exists():
        return []
    cases: list[dict[str, object]] = []
    for path in sorted(cases_root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        case = {
            "case_id": str(payload.get("case_id", path.stem)).strip() or path.stem,
            "description": str(payload.get("description", "")).strip(),
            "path": str(payload.get("path", "")).strip(),
            "op": str(payload.get("op", "equals")).strip().lower() or "equals",
            "expected": payload.get("expected"),
        }
        cases.append(case)
    return sorted(cases, key=lambda item: str(item["case_id"]))


def evaluate_regression_cases(
    *,
    report: Mapping[str, object],
    cases: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Evaluate case expectations against one report payload."""
    results: list[dict[str, object]] = []
    passed = 0
    for case in cases:
        case_id = str(case.get("case_id", "unknown")).strip() or "unknown"
        path = str(case.get("path", "")).strip()
        op = str(case.get("op", "equals")).strip().lower() or "equals"
        expected = case.get("expected")
        try:
            actual = _resolve_path(report, path)
            ok = _evaluate(op=op, actual=actual, expected=expected)
            error: str | None = None
        except Exception as exc:  # pragma: no cover - defensive
            actual = None
            ok = False
            error = str(exc)
        if ok:
            passed += 1
        result: dict[str, object] = {
            "case_id": case_id,
            "path": path,
            "op": op,
            "expected": expected,
            "actual": actual,
            "status": "pass" if ok else "fail",
        }
        if error is not None:
            result["error"] = error
        results.append(result)
    total = len(results)
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / total) if total else 1.0,
        "results": results,
        "status": "pass" if failed == 0 else "fail",
    }


def _evaluate(*, op: str, actual: object, expected: object) -> bool:
    if op == "equals":
        return actual == expected
    if op == "not_empty":
        if actual is None:
            return False
        if isinstance(actual, (str, list, dict, tuple, set)):
            return len(actual) > 0
        return True
    if op == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, list):
            return expected in actual
        if isinstance(actual, dict):
            return str(expected) in actual
        return False
    if op == "gte":
        try:
            return _to_float(actual) >= _to_float(expected)
        except (TypeError, ValueError):
            return False
    raise ValueError(f"unsupported_eval_op:{op}")


def _to_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError("value_is_not_numeric")


def _resolve_path(payload: Mapping[str, object], path: str) -> object:
    if not path:
        return payload
    current: object = payload
    for part in path.split("."):
        token = part.strip()
        if not token:
            continue
        if isinstance(current, Mapping):
            if token not in current:
                raise KeyError(f"path_not_found:{path}")
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError as exc:  # pragma: no cover - defensive
                raise KeyError(f"path_not_found:{path}") from exc
            if index < 0 or index >= len(current):
                raise KeyError(f"path_not_found:{path}")
            current = current[index]
            continue
        raise KeyError(f"path_not_found:{path}")
    return current
