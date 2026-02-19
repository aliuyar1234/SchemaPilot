"""Bounded retry policy primitives used by connector wrappers."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Deterministic retry budget for external operations."""

    max_attempts: int
    base_backoff_ms: int
    max_backoff_ms: int
    timeout_seconds: int

    def backoff_for_attempt(self, attempt_number: int) -> float:
        """Return bounded exponential backoff in seconds for one retry attempt."""
        clamped_attempt = max(attempt_number, 1)
        backoff_ms = self.base_backoff_ms * (2 ** (clamped_attempt - 1))
        backoff_ms = min(backoff_ms, self.max_backoff_ms)
        return max(backoff_ms, 0) / 1000.0


def connector_retry_policy_from_env() -> RetryPolicy:
    """Load connector retry policy from environment with safe defaults."""
    max_retries = _env_int("SCHEMAPILOT_CONNECTOR_MAX_RETRIES", default=2)
    max_attempts = max(max_retries + 1, 1)
    return RetryPolicy(
        max_attempts=max_attempts,
        base_backoff_ms=max(_env_int("SCHEMAPILOT_CONNECTOR_RETRY_BACKOFF_MS", default=50), 0),
        max_backoff_ms=max(_env_int("SCHEMAPILOT_CONNECTOR_RETRY_MAX_BACKOFF_MS", default=500), 0),
        timeout_seconds=max(_env_int("SCHEMAPILOT_CONNECTOR_TIMEOUT_SECONDS", default=30), 1),
    )


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default
