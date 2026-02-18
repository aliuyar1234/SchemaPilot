"""Optional OpenTelemetry tracing helpers (disabled by default)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TraceContext:
    """Resolved trace context for one operation."""

    trace_id: str
    enabled: bool
    provider: str


def start_trace(
    *,
    service_name: str,
    operation: str,
    correlation_id: str,
    enabled: bool,
) -> TraceContext:
    """Start lightweight trace context with graceful fallback when OTel is unavailable."""
    if not enabled:
        return TraceContext(trace_id=correlation_id, enabled=False, provider="disabled")
    try:
        from opentelemetry import trace
    except Exception:
        return TraceContext(trace_id=correlation_id, enabled=False, provider="unavailable")
    tracer = trace.get_tracer(service_name)
    span = tracer.start_span(operation)
    try:
        span.set_attribute("schemapilot.correlation_id", correlation_id)
        trace_id = format(span.get_span_context().trace_id, "032x")
        if not trace_id.strip("0"):
            trace_id = correlation_id
    finally:
        span.end()
    return TraceContext(trace_id=trace_id, enabled=True, provider="opentelemetry")
