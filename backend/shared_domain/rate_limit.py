"""In-memory per-actor rate/concurrency limits for gateway fail-closed behavior."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str


class InMemoryActorRateLimiter:
    """Simple fixed-window request limiter with concurrent-request caps."""

    def __init__(
        self,
        *,
        max_requests_per_minute: int,
        max_concurrent_per_actor: int,
    ) -> None:
        self._max_requests_per_minute = max_requests_per_minute
        self._max_concurrent_per_actor = max_concurrent_per_actor
        self._lock = threading.Lock()
        self._window_epoch_minute = int(time.time() // 60)
        self._request_counts: dict[str, int] = {}
        self._inflight_counts: dict[str, int] = {}

    def try_acquire(self, actor_id: str) -> RateLimitDecision:
        with self._lock:
            current_window = int(time.time() // 60)
            if current_window != self._window_epoch_minute:
                self._window_epoch_minute = current_window
                self._request_counts.clear()

            if self._max_concurrent_per_actor <= 0:
                return RateLimitDecision(False, "concurrency_limit_exceeded")
            inflight = self._inflight_counts.get(actor_id, 0)
            if inflight >= self._max_concurrent_per_actor:
                return RateLimitDecision(False, "concurrency_limit_exceeded")

            if self._max_requests_per_minute <= 0:
                return RateLimitDecision(False, "rate_limit_exceeded")
            request_count = self._request_counts.get(actor_id, 0)
            if request_count >= self._max_requests_per_minute:
                return RateLimitDecision(False, "rate_limit_exceeded")

            self._request_counts[actor_id] = request_count + 1
            self._inflight_counts[actor_id] = inflight + 1
            return RateLimitDecision(True, "allow")

    def release(self, actor_id: str) -> None:
        with self._lock:
            inflight = self._inflight_counts.get(actor_id, 0)
            if inflight <= 1:
                self._inflight_counts.pop(actor_id, None)
            else:
                self._inflight_counts[actor_id] = inflight - 1
