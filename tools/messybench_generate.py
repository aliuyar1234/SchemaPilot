#!/usr/bin/env python3
"""Generate bounded MessyBench datasets and ground truth."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def generate_dataset(output_root: Path) -> dict[str, object]:
    """Generate deterministic messy datasets and return ground truth."""
    data_dir = output_root / "datasets"
    data_dir.mkdir(parents=True, exist_ok=True)

    invoices_eu = data_dir / "invoices_eu.csv"
    invoices_us = data_dir / "invoices_us.csv"
    customers = data_dir / "customers_export.csv"

    with invoices_eu.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["invoice_id", "customer_id", "amount_eur", "issued_on"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "invoice_id": "INV-1",
                "customer_id": "C-1",
                "amount_eur": "99.50",
                "issued_on": "2024-01-01",
            }
        )
        writer.writerow(
            {
                "invoice_id": "INV-2",
                "customer_id": "C-2",
                "amount_eur": "150.00",
                "issued_on": "2024-01-02",
            }
        )

    with invoices_us.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Invoice ID", "Customer-ID", "Amount USD", "Issue Date"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Invoice ID": "INV-3",
                "Customer-ID": "C-3",
                "Amount USD": "200.00",
                "Issue Date": "01/03/2024",
            }
        )
        writer.writerow(
            {
                "Invoice ID": "INV-4",
                "Customer-ID": "C-4",
                "Amount USD": "175.25",
                "Issue Date": "01/04/2024",
            }
        )

    with customers.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["customer_id", "email", "region"])
        writer.writeheader()
        writer.writerow({"customer_id": "C-1", "email": "alice@example.com", "region": "eu"})
        writer.writerow({"customer_id": "C-2", "email": "bob@example.com", "region": "us"})

    return {
        "dataset_names": ["invoices_eu.csv", "invoices_us.csv", "customers_export.csv"],
        "expected_family_keys": ["customers", "invoices"],
        "expected_invoice_pk": "invoice_id",
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output_root = root / "runtime" / "messybench"
    output_root.mkdir(parents=True, exist_ok=True)

    ground_truth = generate_dataset(output_root)
    ground_truth_path = output_root / "ground_truth.json"
    ground_truth_path.write_text(
        json.dumps(ground_truth, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(ground_truth_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
