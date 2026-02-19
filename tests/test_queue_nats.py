from __future__ import annotations

from backend.workers.queue_nats import NatsQueueConfig, poll_run_ids, validate_nats_config


def test_validate_nats_config_requires_url_when_enabled() -> None:
    config = NatsQueueConfig(enabled=True, url=None)
    try:
        validate_nats_config(config)
    except ValueError as exc:
        assert str(exc) == "nats_url_required"
    else:  # pragma: no cover
        raise AssertionError("expected nats_url_required")


def test_poll_run_ids_returns_empty_placeholder() -> None:
    config = NatsQueueConfig(enabled=True, url="nats://localhost:4222")
    assert poll_run_ids(config, max_items=10) == []

