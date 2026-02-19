"""Optional NATS queue adapter placeholder for enterprise deployments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NatsQueueConfig:
    """NATS queue runtime config."""

    enabled: bool
    url: str | None
    subject: str = "schemapilot.runs"


def validate_nats_config(config: NatsQueueConfig) -> None:
    """Fail closed when NATS backend is enabled without a URL."""
    if config.enabled and not str(config.url or "").strip():
        raise ValueError("nats_url_required")


def poll_run_ids(config: NatsQueueConfig, *, max_items: int) -> list[str]:
    """Poll run IDs from NATS subject.

    Current implementation is intentionally conservative and returns no items; it
    exists to keep queue backend plumbing deterministic and disabled-by-default.
    """
    validate_nats_config(config)
    _ = max(max_items, 0)
    return []

