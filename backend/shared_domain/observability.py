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
AUDIT_WRITE_FAILURES_TOTAL = Counter(
    "schemapilot_audit_write_failures_total",
    "Audit write failures that forced fail-closed behavior.",
    labelnames=("workspace_id", "service", "operation"),
    registry=REGISTRY,
)
AUDIT_SINK_DELIVERY_TOTAL = Counter(
    "schemapilot_audit_sink_delivery_total",
    "Audit sink delivery outcomes from outbox dispatch.",
    labelnames=("service", "result"),
    registry=REGISTRY,
)
AUDIT_OUTBOX_BACKLOG_TOTAL = Gauge(
    "schemapilot_audit_outbox_backlog_total",
    "Pending audit outbox rows per service.",
    labelnames=("service",),
    registry=REGISTRY,
)
AUDIT_SINK_DELIVERY_LATENCY_MS = Histogram(
    "schemapilot_audit_sink_delivery_latency_ms",
    "Audit sink delivery latency in milliseconds.",
    labelnames=("service", "result"),
    registry=REGISTRY,
)
GATEWAY_QUERY_CACHE_TOTAL = Counter(
    "schemapilot_gateway_query_cache_total",
    "Gateway query cache events.",
    labelnames=("workspace_id", "result"),
    registry=REGISTRY,
)
WORKER_STEP_DURATION_MS = Histogram(
    "schemapilot_worker_step_duration_ms",
    "Worker run-step duration in milliseconds.",
    labelnames=("workspace_id", "run_type", "step_key", "result"),
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


def increment_audit_write_failure(*, workspace_id: str, service: str, operation: str) -> None:
    """Increment audit write failure counter."""
    AUDIT_WRITE_FAILURES_TOTAL.labels(
        workspace_id=workspace_id, service=service, operation=operation
    ).inc()


def increment_audit_sink_delivery(*, service: str, result: str) -> None:
    """Increment audit sink delivery counter."""
    AUDIT_SINK_DELIVERY_TOTAL.labels(service=service, result=result).inc()


def set_audit_outbox_backlog(*, service: str, count: int) -> None:
    """Set pending audit outbox backlog gauge."""
    AUDIT_OUTBOX_BACKLOG_TOTAL.labels(service=service).set(count)


def observe_audit_sink_delivery_latency(*, service: str, result: str, latency_ms: float) -> None:
    """Observe audit sink delivery latency."""
    AUDIT_SINK_DELIVERY_LATENCY_MS.labels(service=service, result=result).observe(latency_ms)


def increment_gateway_query_cache(*, workspace_id: str, result: str) -> None:
    """Increment gateway query cache event counter."""
    GATEWAY_QUERY_CACHE_TOTAL.labels(workspace_id=workspace_id, result=result).inc()


def observe_worker_step_duration(
    *, workspace_id: str, run_type: str, step_key: str, result: str, duration_ms: float
) -> None:
    """Observe worker step duration."""
    WORKER_STEP_DURATION_MS.labels(
        workspace_id=workspace_id,
        run_type=run_type,
        step_key=step_key,
        result=result,
    ).observe(max(duration_ms, 0.0))


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
