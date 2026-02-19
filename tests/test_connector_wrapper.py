from __future__ import annotations

from backend.shared_domain.retry_policy import RetryPolicy
from backend.workers.connectors.wrapper import execute_connector_discovery


def test_connector_wrapper_retries_transient_failures_then_succeeds() -> None:
    attempts = {"count": 0}

    def flaky() -> list[dict[str, object]]:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("temporary connection reset")
        return [{"path": "a.csv"}]

    rows, meta = execute_connector_discovery(
        flaky,
        source_type="sharepoint",
        policy=RetryPolicy(
            max_attempts=4,
            base_backoff_ms=0,
            max_backoff_ms=0,
            timeout_seconds=5,
        ),
    )
    assert rows == [{"path": "a.csv"}]
    assert attempts["count"] == 3
    assert meta["attempts"] == 3


def test_connector_wrapper_stops_on_non_retryable_failure() -> None:
    attempts = {"count": 0}

    def non_retryable() -> list[dict[str, object]]:
        attempts["count"] += 1
        raise ValueError("schema invalid")

    try:
        execute_connector_discovery(
            non_retryable,
            source_type="jira",
            policy=RetryPolicy(
                max_attempts=5,
                base_backoff_ms=0,
                max_backoff_ms=0,
                timeout_seconds=5,
            ),
        )
    except ValueError as exc:
        assert "connector_retry_budget_exhausted:jira" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    assert attempts["count"] == 1
