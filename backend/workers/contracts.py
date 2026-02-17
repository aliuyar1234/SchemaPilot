"""Quality contracts and quarantine partition helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractResult:
    """Contract evaluation output."""

    passed_rows: list[dict[str, object]]
    quarantined_rows: list[dict[str, object]]
    failures: list[dict[str, object]]


def evaluate_quality_contracts(
    rows: list[dict[str, object]],
    *,
    required_columns: list[str],
    not_null_columns: list[str],
    unique_columns: list[str],
) -> ContractResult:
    """Evaluate simple schema/not-null/uniqueness contracts."""
    failures: list[dict[str, object]] = []
    quarantined: list[dict[str, object]] = []
    passed: list[dict[str, object]] = []
    unique_seen: dict[str, set[str]] = {column: set() for column in unique_columns}

    for index, row in enumerate(rows):
        row_failures: list[str] = []
        missing = [column for column in required_columns if column not in row]
        if missing:
            row_failures.append(f"missing_columns:{','.join(sorted(missing))}")
        for column in not_null_columns:
            if row.get(column) in (None, ""):
                row_failures.append(f"not_null:{column}")
        for column in unique_columns:
            value = str(row.get(column, ""))
            if value in unique_seen[column]:
                row_failures.append(f"unique:{column}")
            unique_seen[column].add(value)

        if row_failures:
            failures.append({"row_index": index, "reasons": row_failures})
            quarantined.append({**row, "_quarantine_reasons": row_failures})
        else:
            passed.append(row)

    return ContractResult(passed_rows=passed, quarantined_rows=quarantined, failures=failures)
