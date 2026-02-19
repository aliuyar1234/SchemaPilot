"""Standard connector execution wrapper with bounded retries/timeouts."""

from __future__ import annotations

import time
from collections.abc import Callable

from backend.shared_domain.retry_policy import RetryPolicy, connector_retry_policy_from_env


def execute_connector_discovery[T](
    operation: Callable[[], T],
    *,
    source_type: str,
    policy: RetryPolicy | None = None,
) -> tuple[T, dict[str, object]]:
    """Execute one connector operation with deterministic error budgeting."""
    retry_policy = policy or connector_retry_policy_from_env()
    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            value = operation()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return value, {
                "source_type": source_type,
                "attempts": attempt,
                "elapsed_ms": elapsed_ms,
                "retry_policy": {
                    "max_attempts": retry_policy.max_attempts,
                    "timeout_seconds": retry_policy.timeout_seconds,
                },
            }
        except Exception as exc:
            last_error = exc
            elapsed = time.monotonic() - started
            if elapsed >= float(retry_policy.timeout_seconds):
                raise ValueError(
                    f"connector_timeout_exceeded:{source_type}:attempts={attempt}"
                ) from exc
            retryable = _is_retryable_connector_error(exc)
            if not retryable or attempt >= retry_policy.max_attempts:
                raise ValueError(
                    f"connector_retry_budget_exhausted:{source_type}:attempts={attempt}:{exc}"
                ) from exc
            time.sleep(retry_policy.backoff_for_attempt(attempt))
    if last_error is None:  # pragma: no cover
        raise ValueError(f"connector_retry_budget_exhausted:{source_type}:attempts=0")
    raise ValueError(
        f"connector_retry_budget_exhausted:{source_type}:attempts={retry_policy.max_attempts}:{last_error}"
    ) from last_error


def _is_retryable_connector_error(exc: Exception) -> bool:
    message = str(exc).strip().lower()
    transient_tokens = (
        "timeout",
        "temporar",
        "connection",
        "unavailable",
        "refused",
        "reset",
        "429",
        "503",
    )
    return any(token in message for token in transient_tokens)
