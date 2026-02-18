#!/usr/bin/env python3
"""Execute MessyBench generation and evaluation harness."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from time import perf_counter
from typing import cast

from messybench_generate import generate_dataset

from backend.workers.inference import (
    cluster_dataset_families,
    infer_primary_key_candidates,
    infer_relationship_candidates,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regression",
        action="store_true",
        help="Enforce baseline regression thresholds from tools/messybench_baseline.json.",
    )
    return parser.parse_args()


def _load_csv_rows(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _normalize_invoice_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        normalized.append(
            {
                "invoice_id": row.get("invoice_id") or row.get("Invoice ID"),
                "customer_id": row.get("customer_id") or row.get("Customer-ID"),
                "amount": row.get("amount_eur") or row.get("Amount USD"),
            }
        )
    return normalized


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    output_root = root / "runtime" / "messybench"
    output_root.mkdir(parents=True, exist_ok=True)

    started = perf_counter()
    ground_truth = generate_dataset(output_root)
    goldens = json.loads((root / "tools" / "messybench_goldens.json").read_text(encoding="utf-8"))

    dataset_names_raw = ground_truth.get("dataset_names", [])
    if isinstance(dataset_names_raw, list):
        datasets = [str(item) for item in dataset_names_raw]
    else:
        datasets = []
    families = cluster_dataset_families(datasets)
    family_keys = sorted(families.keys())

    invoices_eu_rows = _normalize_invoice_rows(
        _load_csv_rows(output_root / "datasets" / "invoices_eu.csv")
    )
    invoices_us_rows = _normalize_invoice_rows(
        _load_csv_rows(output_root / "datasets" / "invoices_us.csv")
    )
    customers_rows = _load_csv_rows(output_root / "datasets" / "customers_export.csv")

    pk_candidates = infer_primary_key_candidates(
        rows=invoices_eu_rows + invoices_us_rows,
        columns=["invoice_id", "customer_id", "amount"],
    )
    top_pk_column = str(pk_candidates[0]["column"]) if pk_candidates else ""
    relationship = infer_relationship_candidates(
        left_rows=invoices_eu_rows + invoices_us_rows,
        right_rows=customers_rows,
        left_column="customer_id",
        right_column="customer_id",
    )
    overlap_raw = relationship.get("overlap_count", 0)
    overlap_count = int(overlap_raw) if isinstance(overlap_raw, (int, float, str)) else 0
    expected_family_keys = cast(list[str], goldens.get("expected_family_keys", []))
    expected_invoice_pk = str(goldens.get("expected_invoice_pk", ""))

    checks = [
        {
            "id": "family_keys_match",
            "pass": family_keys == sorted(expected_family_keys),
            "actual": family_keys,
            "expected": sorted(expected_family_keys),
        },
        {
            "id": "invoice_pk_candidate",
            "pass": top_pk_column == expected_invoice_pk,
            "actual": top_pk_column,
            "expected": expected_invoice_pk,
        },
        {
            "id": "relationship_overlap_present",
            "pass": overlap_count >= 2,
            "actual": overlap_count,
            "expected_min": 2,
        },
    ]

    passed = all(bool(item["pass"]) for item in checks)
    result = {
        "status": "pass" if passed else "fail",
        "duration_ms": round((perf_counter() - started) * 1000.0, 3),
        "checks": checks,
        "regression_mode": args.regression,
    }
    if args.regression:
        baseline_path = root / "tools" / "messybench_baseline.json"
        if not baseline_path.exists():
            result["status"] = "fail"
            result["regression_error"] = "missing_baseline_file"
        else:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            expected_checks = baseline.get("required_checks", [])
            max_duration_ms = baseline.get("max_duration_ms", 0)
            if not isinstance(expected_checks, list):
                expected_checks = []
            check_map = {str(item.get("id", "")): bool(item.get("pass", False)) for item in checks}
            missing_or_failed = [
                check_id for check_id in expected_checks if not check_map.get(str(check_id), False)
            ]
            if missing_or_failed:
                result["status"] = "fail"
                result["regression_error"] = "required_checks_failed"
                result["failed_required_checks"] = sorted(str(item) for item in missing_or_failed)
            if isinstance(max_duration_ms, (int, float)) and max_duration_ms > 0:
                if float(result["duration_ms"]) > float(max_duration_ms):
                    result["status"] = "fail"
                    result["regression_error"] = "duration_regression"
                    result["max_duration_ms"] = float(max_duration_ms)

    report_path = output_root / "results.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    if not passed:
        print("FAIL MessyBench harness")
        print(report_path.relative_to(root).as_posix())
        return 1

    print("PASS MessyBench harness")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
