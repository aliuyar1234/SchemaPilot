"""Observability helpers: structured logs and Prometheus metrics."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from backend.shared_domain.secrets import redact_secrets

REGISTRY = CollectorRegistry()

INGEST_LAG_SECONDS = Gauge(
    "schemapilot_ingest_lag_seconds",
    "Lag between source update and ingest completion.",
    labelnames=("workspace_id", "source_id"),
    registry=REGISTRY,
)
PARSE_FAILURES_TOTAL = Counter(
    "schemapilot_parse_failures_total",
    "Total parse failures.",
    labelnames=("workspace_id", "source_type", "dataset_id"),
    registry=REGISTRY,
)
PROFILING_COVERAGE_RATIO = Gauge(
    "schemapilot_profiling_coverage_ratio",
    "Ratio of datasets covered by profiling.",
    labelnames=("workspace_id",),
    registry=REGISTRY,
)
DRIFT_EVENTS_TOTAL = Counter(
    "schemapilot_drift_events_total",
    "Total schema drift events.",
    labelnames=("workspace_id", "severity"),
    registry=REGISTRY,
)
SILVER_QUARANTINE_ROWS_TOTAL = Counter(
    "schemapilot_silver_quarantine_rows_total",
    "Rows sent to silver quarantine.",
    labelnames=("workspace_id", "entity_name"),
    registry=REGISTRY,
)
CONTRACT_FAILURES_TOTAL = Counter(
    "schemapilot_contract_failures_total",
    "Total contract failures by layer.",
    labelnames=("workspace_id", "layer"),
    registry=REGISTRY,
)
REVIEW_QUEUE_BACKLOG_TOTAL = Gauge(
    "schemapilot_review_queue_backlog_total",
    "Current review queue backlog by priority.",
    labelnames=("workspace_id", "priority"),
    registry=REGISTRY,
)
QUERY_LATENCY_MS = Histogram(
    "schemapilot_query_latency_ms",
    "Gateway query latency in milliseconds.",
    labelnames=("workspace_id", "engine", "result"),
    registry=REGISTRY,
)
POLICY_DENIALS_TOTAL = Counter(
    "schemapilot_policy_denials_total",
    "Policy denial count.",
    labelnames=("workspace_id", "reason"),
    registry=REGISTRY,
)
COST_BYTES_SCANNED_TOTAL = Counter(
    "schemapilot_cost_bytes_scanned_total",
    "Estimated bytes scanned by query execution.",
    labelnames=("workspace_id", "engine"),
    registry=REGISTRY,
)

LOGGER = logging.getLogger("schemapilot")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)


def render_metrics() -> tuple[bytes, str]:
    """Return metrics payload and media type for FastAPI responses."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def observe_query_latency(
    *, workspace_id: str, engine: str, result: str, latency_ms: float
) -> None:
    """Observe query latency."""
    QUERY_LATENCY_MS.labels(workspace_id=workspace_id, engine=engine, result=result).observe(
        latency_ms
    )


def increment_policy_denial(*, workspace_id: str, reason: str) -> None:
    """Increment policy denial counter."""
    POLICY_DENIALS_TOTAL.labels(workspace_id=workspace_id, reason=reason).inc()


def increment_cost_bytes_scanned(*, workspace_id: str, engine: str, bytes_scanned: int) -> None:
    """Increment estimated bytes scanned."""
    COST_BYTES_SCANNED_TOTAL.labels(workspace_id=workspace_id, engine=engine).inc(bytes_scanned)


def increment_contract_failure(*, workspace_id: str, layer: str) -> None:
    """Increment contract failures."""
    CONTRACT_FAILURES_TOTAL.labels(workspace_id=workspace_id, layer=layer).inc()


def set_review_queue_backlog(*, workspace_id: str, priority: str, count: int) -> None:
    """Set review queue backlog gauge."""
    REVIEW_QUEUE_BACKLOG_TOTAL.labels(workspace_id=workspace_id, priority=priority).set(count)


def build_structured_log(
    *,
    level: str,
    msg: str,
    service: str,
    correlation_id: str,
    workspace_id: str | None = None,
    actor_id: str | None = None,
    event_type: str | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build log payload using required fields from observability spec."""
    payload: dict[str, object] = {
        "level": level,
        "msg": msg,
        "service": service,
        "correlation_id": correlation_id,
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "event_type": event_type,
    }
    if extra:
        payload.update(extra)
    return payload


def log_structured_event(
    *,
    level: str,
    msg: str,
    service: str,
    correlation_id: str,
    workspace_id: str | None = None,
    actor_id: str | None = None,
    event_type: str | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Emit redacted JSON log message and return payload."""
    payload = build_structured_log(
        level=level,
        msg=msg,
        service=service,
        correlation_id=correlation_id,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event_type=event_type,
        extra=extra,
    )
    level_value = getattr(logging, level.upper(), logging.INFO)
    serialized = redact_secrets(json.dumps(payload, sort_keys=True, default=str))
    LOGGER.log(level_value, serialized)
    return payload
