"""Dataset profiling and evidence bundle helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from backend.workers.parsing import normalize_text, open_csv_reader_with_fallback


@dataclass(frozen=True)
class ProfileEvidence:
    """Profiling evidence summary."""

    schema_columns: list[str]
    row_count_sampled: int
    null_rates: dict[str, float]
    unique_ratio: dict[str, float]
    parse_error_rate: float

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_columns": self.schema_columns,
            "row_count_sampled": self.row_count_sampled,
            "null_rates": self.null_rates,
            "unique_ratio": self.unique_ratio,
            "parse_error_rate": self.parse_error_rate,
        }


def profile_csv_file(path: str, sample_limit: int = 1000) -> ProfileEvidence:
    """Profile a CSV file with bounded sampling."""
    handle, reader = open_csv_reader_with_fallback(path)
    with handle:
        columns = list(reader.fieldnames or [])
        null_counts = Counter({column: 0 for column in columns})
        unique_values: dict[str, set[str]] = {column: set() for column in columns}
        parse_errors = 0
        row_count = 0
        for row in reader:
            if row_count >= sample_limit:
                break
            row_count += 1
            for column in columns:
                value = normalize_text(str(row.get(column) or ""))
                if value == "":
                    null_counts[column] += 1
                unique_values[column].add(value)
            if len(row) != len(columns):
                parse_errors += 1
    null_rates = {
        column: (null_counts[column] / row_count if row_count else 0.0) for column in columns
    }
    unique_ratio = {
        column: (len(unique_values[column]) / row_count if row_count else 0.0) for column in columns
    }
    parse_error_rate = parse_errors / row_count if row_count else 0.0
    return ProfileEvidence(
        schema_columns=columns,
        row_count_sampled=row_count,
        null_rates=null_rates,
        unique_ratio=unique_ratio,
        parse_error_rate=parse_error_rate,
    )


def write_evidence_bundle(
    *,
    workspace_id: str,
    dataset_id: str,
    evidence: ProfileEvidence,
    output_root: str,
) -> str:
    """Persist evidence bundle to deterministic path."""
    root = Path(output_root) / "evidence" / workspace_id / dataset_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / "profile_evidence.json"
    path.write_text(json.dumps(evidence.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path.as_posix()


def build_dataset_card(
    *,
    dataset_id: str,
    evidence: ProfileEvidence,
    drift: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build lightweight dataset card for UI summary."""
    return {
        "dataset_id": dataset_id,
        "columns": evidence.schema_columns,
        "row_count_sampled": evidence.row_count_sampled,
        "parse_error_rate": evidence.parse_error_rate,
        "drift": drift or {"severity": "none"},
    }
