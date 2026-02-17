from __future__ import annotations

from backend.workers.inference import (
    cluster_dataset_families,
    infer_primary_key_candidates,
    infer_relationship_candidates,
)


def test_schema_inference_clusters_dataset_families() -> None:
    clusters = cluster_dataset_families(
        ["orders_2025.csv", "orders_2026.csv", "customers_2026.csv"]
    )
    assert "orders" in clusters
    assert len(clusters["orders"]) == 2


def test_key_and_relationship_inference() -> None:
    left = [{"id": "1", "customer_id": "A"}, {"id": "2", "customer_id": "B"}]
    right = [{"customer_id": "A"}, {"customer_id": "C"}]
    pk_candidates = infer_primary_key_candidates(left, ["id", "customer_id"])
    assert pk_candidates[0]["column"] == "id"
    rel = infer_relationship_candidates(left, right, "customer_id", "customer_id")
    assert rel["overlap_count"] == 1
