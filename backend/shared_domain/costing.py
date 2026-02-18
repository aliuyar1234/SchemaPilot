"""Simple deterministic cost estimation and budget enforcement helpers."""

from __future__ import annotations


def estimate_query_cost_bytes(*, query_text: str, row_count: int, column_count: int) -> int:
    """Estimate logical bytes scanned/processed for SQL responses."""
    query_bytes = max(len(query_text.encode("utf-8")), 1)
    row_weight = max(row_count, 0) * max(column_count, 1) * 32
    return query_bytes + row_weight


def estimate_retrieval_cost_bytes(*, query_text: str, result_count: int) -> int:
    """Estimate logical bytes processed for retrieval responses."""
    query_bytes = max(len(query_text.encode("utf-8")), 1)
    return query_bytes + (max(result_count, 0) * 256)


def enforce_budget(*, estimated_bytes: int, budget_bytes: int) -> bool:
    """Return whether estimated bytes stay within configured budget."""
    return estimated_bytes <= max(budget_bytes, 0)

