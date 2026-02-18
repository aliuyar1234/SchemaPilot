"""Policy-aware in-memory query cache for gateway SQL responses."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class QueryCacheHit:
    """Cached query payload and metadata."""

    value: dict[str, Any]
    expires_at: float


class InMemoryQueryCache:
    """Small in-memory TTL cache with deterministic key/value handling."""

    def __init__(self, *, enabled: bool, ttl_seconds: int, max_entries: int = 1024) -> None:
        self.enabled = enabled
        self.ttl_seconds = max(ttl_seconds, 1)
        self.max_entries = max(max_entries, 1)
        self._entries: dict[str, QueryCacheHit] = {}
        self._lock = Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        """Return cached value if enabled and entry is fresh."""
        if not self.enabled:
            return None
        now = time.time()
        with self._lock:
            hit = self._entries.get(key)
            if hit is None:
                return None
            if hit.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return dict(hit.value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Persist one cache entry when enabled."""
        if not self.enabled:
            return
        now = time.time()
        expires_at = now + float(self.ttl_seconds)
        with self._lock:
            if len(self._entries) >= self.max_entries:
                oldest_key = min(self._entries, key=lambda item: self._entries[item].expires_at)
                self._entries.pop(oldest_key, None)
            self._entries[key] = QueryCacheHit(value=dict(value), expires_at=expires_at)

    def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate entries by deterministic key prefix."""
        with self._lock:
            doomed = [key for key in self._entries if key.startswith(prefix)]
            for key in doomed:
                self._entries.pop(key, None)
