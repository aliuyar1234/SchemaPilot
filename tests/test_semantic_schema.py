from __future__ import annotations

from copy import deepcopy

import pytest

from backend.shared_domain.semantic import semantic_manifest_checksum, validate_semantic_manifest


def _valid_manifest() -> dict[str, object]:
    return {
        "manifest_version": "1",
        "workspace_id": "workspace_semantic",
        "entities": [
            {
                "entity_id": "invoice",
                "dataset_id": "dataset_invoice",
                "primary_key": "invoice_id",
                "attributes": ["invoice_date", "customer_id"],
            },
            {
                "entity_id": "customer",
                "dataset_id": "dataset_customer",
                "primary_key": "customer_id",
                "attributes": ["customer_name"],
            },
        ],
        "metrics": [
            {
                "metric_id": "gross_revenue",
                "entity_id": "invoice",
                "aggregation": "sum",
                "field": "amount",
                "expression": "sum(amount)",
            },
            {
                "metric_id": "invoice_count",
                "entity_id": "invoice",
                "aggregation": "count",
                "field": "invoice_id",
                "expression": "count(invoice_id)",
            },
        ],
        "joins": [
            {
                "join_id": "invoice_customer",
                "left_entity_id": "invoice",
                "right_entity_id": "customer",
                "left_key": "customer_id",
                "right_key": "customer_id",
                "join_type": "inner",
            }
        ],
    }


def test_validate_semantic_manifest_normalizes_and_hashes_deterministically() -> None:
    source = _valid_manifest()
    source["metrics"] = list(reversed(source["metrics"]))  # type: ignore[index]
    normalized = validate_semantic_manifest(source, expected_workspace_id="workspace_semantic")
    assert normalized["manifest_version"] == "1"
    assert [row["metric_id"] for row in normalized["metrics"]] == [  # type: ignore[index]
        "gross_revenue",
        "invoice_count",
    ]
    checksum_1 = semantic_manifest_checksum(normalized)
    checksum_2 = semantic_manifest_checksum(deepcopy(normalized))
    assert checksum_1 == checksum_2


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda manifest: manifest["entities"].append(  # type: ignore[index]
                {
                    "entity_id": "invoice",
                    "dataset_id": "dataset_other",
                    "primary_key": "invoice_id",
                    "attributes": [],
                }
            ),
            "duplicate_entity_id",
        ),
        (
            lambda manifest: manifest["metrics"].append(  # type: ignore[index]
                {
                    "metric_id": "orphan_metric",
                    "entity_id": "unknown_entity",
                    "aggregation": "sum",
                    "field": "amount",
                    "expression": "sum(amount)",
                }
            ),
            "metric_entity_not_found",
        ),
        (
            lambda manifest: manifest["joins"].append(  # type: ignore[index]
                {
                    "join_id": "broken_join",
                    "left_entity_id": "invoice",
                    "right_entity_id": "missing_entity",
                    "left_key": "customer_id",
                    "right_key": "customer_id",
                    "join_type": "inner",
                }
            ),
            "join_entity_not_found",
        ),
    ],
)
def test_validate_semantic_manifest_rejects_invalid_shapes(mutator, expected_error: str) -> None:
    manifest = _valid_manifest()
    mutator(manifest)
    with pytest.raises(ValueError, match=expected_error):
        validate_semantic_manifest(manifest, expected_workspace_id="workspace_semantic")


def test_validate_semantic_manifest_rejects_workspace_mismatch() -> None:
    manifest = _valid_manifest()
    with pytest.raises(ValueError, match="workspace_mismatch"):
        validate_semantic_manifest(manifest, expected_workspace_id="other_workspace")
