"""Query gateway FastAPI application."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.gateway.abac import apply_mask, evaluate_abac
from backend.gateway.executor import QueryTimeoutError, UnsafeSqlError, execute_sql
from backend.gateway.policy import AccessDecision, evaluate_access
from backend.gateway.query_cache import InMemoryQueryCache
from backend.gateway.retrieval_opensearch import (
    OpenSearchUnavailableError,
    search_opensearch_documents,
)
from backend.gateway.retrieval_qdrant import QdrantUnavailableError, search_qdrant_documents
from backend.gateway.semantic_binding import SemanticQueryBinding, bind_semantic_query
from backend.shared_domain.audit_models import AccessDecision as AccessDecisionRow
from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.audit_outbox import (
    dispatch_audit_outbox_batch,
    enqueue_audit_outbox_event,
)
from backend.shared_domain.audit_sinks import (
    AuditSink,
    AuditSinkError,
    DisabledAuditSink,
    load_audit_sink,
)
from backend.shared_domain.auth import authenticated_actor_from_request, load_local_auth_tokens
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.costing import (
    enforce_budget,
    estimate_query_cost_bytes,
    estimate_retrieval_cost_bytes,
)
from backend.shared_domain.db import get_session_factory, prepare_database
from backend.shared_domain.embeddings_provider import load_embeddings_provider
from backend.shared_domain.errors import (
    DisabledIntegrationError,
    PolicyDeniedError,
    SchemaPilotError,
)
from backend.shared_domain.gold_pointer import load_latest_gold_pointer
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import CatalogDataset, GovernancePolicy
from backend.shared_domain.observability import (
    increment_audit_write_failure,
    increment_cost_bytes_scanned,
    increment_gateway_query_cache,
    increment_policy_denial,
    log_structured_event,
    observe_query_latency,
    render_metrics,
)
from backend.shared_domain.provenance import build_provenance_v1
from backend.shared_domain.rate_limit import InMemoryActorRateLimiter
from backend.shared_domain.retrieval import load_retrieval_corpus, retrieve_documents
from backend.shared_domain.tracing import start_trace

_ACTIVE_AUDIT_SINK: AuditSink = DisabledAuditSink()
_AUDIT_SINK_MODE: str = "outbox"
_AUDIT_OUTBOX_DISPATCH_BATCH_SIZE: int = 100
_AUDIT_OUTBOX_MAX_ATTEMPTS: int = 5


def create_gateway_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create gateway app with deny-by-default behavior."""
    settings = settings_factory()
    settings.validate()
    global _ACTIVE_AUDIT_SINK  # noqa: PLW0603
    global _AUDIT_SINK_MODE  # noqa: PLW0603
    global _AUDIT_OUTBOX_DISPATCH_BATCH_SIZE  # noqa: PLW0603
    global _AUDIT_OUTBOX_MAX_ATTEMPTS  # noqa: PLW0603
    _ACTIVE_AUDIT_SINK = load_audit_sink(settings)
    _AUDIT_SINK_MODE = settings.audit_sink_mode
    _AUDIT_OUTBOX_DISPATCH_BATCH_SIZE = settings.audit_outbox_dispatch_batch_size
    _AUDIT_OUTBOX_MAX_ATTEMPTS = settings.audit_outbox_max_attempts
    embeddings_provider = load_embeddings_provider(
        provider_name=settings.embeddings_provider,
        dimensions=settings.embeddings_dimensions,
    )
    session_factory = get_session_factory(settings.database_url)
    prepare_database(settings)
    auth_tokens = load_local_auth_tokens()
    rate_limiter = InMemoryActorRateLimiter(
        max_requests_per_minute=_env_int("SCHEMAPILOT_GATEWAY_MAX_REQUESTS_PER_MINUTE", 120),
        max_concurrent_per_actor=_env_int("SCHEMAPILOT_GATEWAY_MAX_CONCURRENT_PER_ACTOR", 4),
    )
    query_cache = InMemoryQueryCache(
        enabled=settings.gateway_query_cache_enabled,
        ttl_seconds=settings.gateway_query_cache_ttl_seconds,
        max_entries=settings.gateway_query_cache_max_entries,
    )
    app = FastAPI(title="SchemaPilot Gateway", version="0.1.0")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id", new_ulid())
        request.state.request_id = request_id
        trace_context = start_trace(
            service_name=settings.tracing_service_name,
            operation=f"{request.method}:{request.url.path}",
            correlation_id=request_id,
            enabled=settings.tracing_enabled,
        )
        request.state.trace_id = trace_context.trace_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-trace-id"] = trace_context.trace_id
        log_structured_event(
            level="info",
            msg="request.completed",
            service="gateway",
            correlation_id=request_id,
            event_type="http.request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
            },
        )
        if _AUDIT_SINK_MODE == "outbox":
            try:
                dispatch_audit_outbox_batch(
                    session_factory=session_factory,
                    sink=_ACTIVE_AUDIT_SINK,
                    service="gateway",
                    max_batch=_AUDIT_OUTBOX_DISPATCH_BATCH_SIZE,
                    max_attempts=_AUDIT_OUTBOX_MAX_ATTEMPTS,
                )
            except Exception as exc:  # pragma: no cover - defensive runtime fallback
                log_structured_event(
                    level="error",
                    msg="audit.outbox_dispatch_failed",
                    service="gateway",
                    correlation_id=request_id,
                    event_type="audit.outbox_dispatch_failed",
                    extra={"error": str(exc)},
                )
        return response

    @app.exception_handler(SchemaPilotError)
    async def schemapilot_error_handler(request: Request, exc: SchemaPilotError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_ulid())
        return JSONResponse(
            status_code=403 if exc.error_code == "POLICY_DENIED" else 400,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": str(exc),
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "gateway",
            "profile": settings.profile,
            "bind_address": settings.bind_address,
        }

    @app.get("/api/v1/metrics")
    async def metrics() -> Response:
        payload, media_type = render_metrics()
        return Response(content=payload, media_type=media_type)

    @app.post("/api/v1/gateway/query")
    async def query(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        effective_policy_pack = _load_effective_policy_pack(
            session_factory=session_factory,
            workspace_id=workspace_id,
        )
        request_context = _request_context(payload)
        actor_dict = authenticated_actor_from_request(
            request,
            settings=settings,
            auth_tokens=auth_tokens,
        )
        policy_decision_id = new_ulid()

        if actor_dict is None:
            reason = "missing_or_invalid_auth_token"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id="unknown",
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        actor_attributes_raw = actor_dict.get("attributes", {})
        actor_attributes = actor_attributes_raw if isinstance(actor_attributes_raw, dict) else {}
        allowlisted_ai = bool(actor_attributes.get("ai_allowlisted", False))
        decision = evaluate_access(actor_dict, allow_ai=allowlisted_ai)
        if decision.result != "allow":
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result=decision.result,
                reason=decision.reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=decision.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": decision.reason, "policy_decision_id": policy_decision_id},
            )
        actor_id = str(actor_dict.get("actor_id", "unknown"))
        rate_limit_decision = rate_limiter.try_acquire(actor_id)
        if not rate_limit_decision.allowed:
            reason = rate_limit_decision.reason
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=actor_id,
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        resource_attributes = payload.get("resource_attributes", {})
        resource_attrs = resource_attributes if isinstance(resource_attributes, dict) else {}
        actor_type = str(actor_dict.get("actor_type", "human")).lower()
        semantic_binding: SemanticQueryBinding | None = None
        datasets_used: list[str] = []
        query_payload = payload.get("query", {})
        query_text = ""
        if isinstance(query_payload, dict):
            query_text = str(query_payload.get("text", ""))
        if actor_type == "ai":
            semantic_payload_raw = payload.get("semantic_query")
            if not isinstance(semantic_payload_raw, dict) or not semantic_payload_raw:
                reason = "semantic_query_required"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query"},
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
            semantic_payload = semantic_payload_raw
            try:
                semantic_binding = bind_semantic_query(
                    session_factory=session_factory,
                    workspace_id=workspace_id,
                    semantic_query=semantic_payload,
                )
            except ValueError as exc:
                reason = str(exc) if str(exc).startswith("semantic_") else "semantic_query_invalid"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query"},
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={
                        "reason": reason,
                        "policy_decision_id": policy_decision_id,
                        "error": str(exc),
                    },
                ) from exc
            query_text = semantic_binding.sql_text
            datasets_used = list(semantic_binding.dataset_ids)
            allowed_raw = actor_attributes.get("allowed_dataset_ids", [])
            allowed = (
                {str(item) for item in allowed_raw} if isinstance(allowed_raw, list) else set()
            )
            cross_workspace_dataset_ids = sorted(
                dataset_id
                for dataset_id in datasets_used
                if _dataset_belongs_to_other_workspace(
                    session_factory=session_factory,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                )
            )
            if cross_workspace_dataset_ids:
                reason = "dataset_workspace_mismatch"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={
                        "endpoint": "query",
                        "dataset_ids": datasets_used,
                        "cross_workspace_dataset_ids": cross_workspace_dataset_ids,
                    },
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
            denied_dataset_ids = sorted(
                dataset_id for dataset_id in datasets_used if dataset_id not in allowed
            )
            if denied_dataset_ids:
                reason = "dataset_not_allowed"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={
                        "endpoint": "query",
                        "dataset_ids": datasets_used,
                        "denied_dataset_ids": denied_dataset_ids,
                    },
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.query",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="sql",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
        else:
            dataset_ref = resource_attrs.get("dataset_id")
            if dataset_ref is not None:
                datasets_used.append(str(dataset_ref))
        abac_mode = str(payload.get("abac_mode", "internal"))
        abac = evaluate_abac(actor=actor_dict, resource_attributes=resource_attrs, mode=abac_mode)
        if not abac.allow:
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=abac.reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=abac.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by ABAC",
                details={"reason": abac.reason, "policy_decision_id": policy_decision_id},
            )

        constraints = payload.get("constraints", {})
        max_rows = 1000
        timeout_ms = 5000
        if isinstance(constraints, dict):
            max_rows_raw = constraints.get("max_rows", 1000)
            if isinstance(max_rows_raw, (int, float, str)):
                max_rows = int(max_rows_raw)
            timeout_raw = constraints.get("timeout_ms", 5000)
            if isinstance(timeout_raw, (int, float, str)):
                timeout_ms = int(timeout_raw)
        query_cache_key = _build_query_cache_key(
            workspace_id=workspace_id,
            actor_id=actor_id,
            actor_roles=actor_dict.get("roles", []),
            actor_attributes=actor_attributes,
            query_text=query_text,
            datasets_used=datasets_used,
            row_filter=abac.row_filter,
            masks=abac.masks,
            max_rows=max_rows,
            timeout_ms=timeout_ms,
            query_engine=settings.query_engine,
            policy_pack=effective_policy_pack,
            storage_root=settings.storage_root,
        )
        cached_payload = query_cache.get(query_cache_key)
        if cached_payload is not None:
            increment_gateway_query_cache(workspace_id=workspace_id, result="hit")
            result_columns = (
                cached_payload.get("columns", [])
                if isinstance(cached_payload.get("columns", []), list)
                else []
            )
            masked_rows = (
                cached_payload.get("rows", [])
                if isinstance(cached_payload.get("rows", []), list)
                else []
            )
        else:
            increment_gateway_query_cache(workspace_id=workspace_id, result="miss")
            try:
                try:
                    result_set = execute_sql(
                        query_text or "select 1 as one",
                        max_rows=max_rows,
                        row_filter=abac.row_filter,
                        timeout_ms=timeout_ms,
                        workspace_id=workspace_id,
                        storage_root=settings.storage_root,
                        query_engine=settings.query_engine,
                        trino_url=settings.trino_url,
                        trino_user=settings.trino_user,
                        trino_catalog=settings.trino_catalog,
                        trino_schema=settings.trino_schema,
                    )
                except UnsafeSqlError as exc:
                    reason = "sql_unsafe"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={"endpoint": "query", "query_text": query_text},
                        applied_filters=_serialize_row_filter(abac.row_filter),
                        applied_masks=abac.masks,
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.query",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="sql",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={
                            "reason": reason,
                            "policy_decision_id": policy_decision_id,
                            "error": str(exc),
                        },
                    ) from exc
                except QueryTimeoutError as exc:
                    reason = "query_timeout"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={"endpoint": "query", "query_text": query_text},
                        applied_filters=_serialize_row_filter(abac.row_filter),
                        applied_masks=abac.masks,
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.query",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="sql",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={
                            "reason": reason,
                            "policy_decision_id": policy_decision_id,
                            "error": str(exc),
                        },
                    ) from exc
                except Exception as exc:  # pragma: no cover - exercised by API tests
                    reason = (
                        "abac_filter_not_enforceable"
                        if abac.row_filter is not None
                        else "query_error"
                    )
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={"endpoint": "query", "query_text": query_text},
                        applied_filters=_serialize_row_filter(abac.row_filter),
                        applied_masks=abac.masks,
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.query",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="sql",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    if abac.row_filter is not None:
                        raise PolicyDeniedError(
                            "Access denied by ABAC",
                            details={
                                "reason": reason,
                                "policy_decision_id": policy_decision_id,
                                "error": str(exc),
                            },
                        ) from exc
                    raise
            finally:
                rate_limiter.release(actor_id)
            increment_cost_bytes_scanned(
                workspace_id=workspace_id,
                engine="sql",
                bytes_scanned=max(len(query_text.encode("utf-8")), 1),
            )
            masked_rows = []
            result_columns = list(result_set.columns)
            column_names = [column["name"] for column in result_set.columns]
            for row in result_set.rows:
                masked_row = []
                for idx, value in enumerate(row):
                    column_name = (
                        str(column_names[idx]) if idx < len(column_names) else f"col_{idx}"
                    )
                    mask_mode = abac.masks.get(column_name)
                    masked_row.append(apply_mask(value, mask_mode) if mask_mode else value)
                masked_rows.append(masked_row)
            query_cache.set(
                query_cache_key,
                {"columns": result_columns, "rows": masked_rows},
            )
            increment_gateway_query_cache(workspace_id=workspace_id, result="store")
        if cached_payload is not None:
            rate_limiter.release(actor_id)
            increment_cost_bytes_scanned(
                workspace_id=workspace_id,
                engine="sql",
                bytes_scanned=max(len(query_text.encode("utf-8")), 1),
            )
        estimated_query_bytes = estimate_query_cost_bytes(
            query_text=query_text,
            row_count=len(masked_rows),
            column_count=len(result_columns),
        )
        if not enforce_budget(
            estimated_bytes=estimated_query_bytes,
            budget_bytes=settings.query_max_bytes,
        ):
            reason = "query_budget_exceeded"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={
                    "endpoint": "query",
                    "estimated_query_bytes": estimated_query_bytes,
                    "query_budget_bytes": settings.query_max_bytes,
                },
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                    "estimated_query_bytes": estimated_query_bytes,
                    "query_budget_bytes": settings.query_max_bytes,
                },
            )

        build_id = new_ulid()
        query_id = new_ulid()
        try:
            provenance = build_provenance_v1(
                workspace_id=workspace_id,
                policy_decision_id=policy_decision_id,
                query_id=query_id,
                build_id=build_id,
                datasets_used=datasets_used,
                snapshots=[],
                decision_reason="allow",
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_pack=effective_policy_pack,
            )
        except ValueError as exc:
            reason = "provenance_unavailable"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "query"},
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.query",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="sql",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                    "error": str(exc),
                },
            ) from exc

        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result="allow",
            reason="allow",
            request_context=request_context,
            resources={
                "endpoint": "query",
                "query_text": query_text,
                "dataset_ids": datasets_used,
                "semantic_metric_id": (
                    semantic_binding.metric_id if semantic_binding is not None else None
                ),
                "semantic_group_by": (
                    semantic_binding.group_by if semantic_binding is not None else []
                ),
                "semantic_manifest_checksum": (
                    semantic_binding.manifest_checksum if semantic_binding is not None else None
                ),
                "policy_pack": effective_policy_pack,
                "query_engine_metadata": (
                    result_set.execution_metadata if cached_payload is None else {}
                ),
            },
            applied_filters=_serialize_row_filter(abac.row_filter),
            applied_masks=abac.masks,
            policy_decision_id=policy_decision_id,
            event_type="gateway.query",
            correlation_id=request.state.request_id,
        )
        observe_query_latency(
            workspace_id=workspace_id,
            engine="sql",
            result="allow",
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )

        response_payload = {
            "result": {
                "columns": result_columns,
                "rows": masked_rows,
                "row_count": len(masked_rows),
            },
            "provenance": provenance,
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }
        if semantic_binding is not None:
            response_payload["semantic"] = {
                "metric_id": semantic_binding.metric_id,
                "group_by": semantic_binding.group_by,
                "manifest_checksum": semantic_binding.manifest_checksum,
            }
        return response_payload

    @app.post("/api/v1/gateway/policy/simulate")
    async def policy_simulate(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        request_context = _request_context(payload)
        policy_decision_id = new_ulid()
        actor_dict = authenticated_actor_from_request(
            request,
            settings=settings,
            auth_tokens=auth_tokens,
        )
        if actor_dict is None:
            reason = "missing_or_invalid_auth_token"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id="unknown",
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "policy_simulate"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.policy_simulate",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        caller_roles_raw = actor_dict.get("roles", [])
        caller_roles = (
            {str(item) for item in caller_roles_raw}
            if isinstance(caller_roles_raw, list)
            else set()
        )
        if not caller_roles.intersection({"data_steward", "platform_admin"}):
            reason = "simulation_forbidden"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "policy_simulate"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.policy_simulate",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        actor_preview_raw = payload.get("actor", actor_dict)
        actor_preview = actor_preview_raw if isinstance(actor_preview_raw, dict) else actor_dict
        resource_attributes_raw = payload.get("resource_attributes", {})
        resource_attributes = (
            resource_attributes_raw if isinstance(resource_attributes_raw, dict) else {}
        )
        actor_attributes = actor_preview.get("attributes")
        allowlisted_ai = bool(
            isinstance(actor_attributes, dict) and actor_attributes.get("ai_allowlisted", False)
        )
        access = evaluate_access(actor_preview, allow_ai=allowlisted_ai)
        abac_mode = str(payload.get("abac_mode", "internal"))
        abac = evaluate_abac(
            actor=actor_preview,
            resource_attributes=resource_attributes,
            mode=abac_mode,
        )
        result = "allow" if access.result == "allow" and abac.allow else "deny"
        reason = "allow"
        if result == "deny":
            reason = abac.reason if access.result == "allow" else access.reason
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result=result,
            reason=reason,
            request_context=request_context,
            resources={
                "endpoint": "policy_simulate",
                "action": str(payload.get("action", "query")),
                "actor_preview": {
                    "actor_type": str(actor_preview.get("actor_type", "human")),
                    "roles": actor_preview.get("roles", []),
                },
            },
            applied_filters=_serialize_row_filter(abac.row_filter),
            applied_masks=abac.masks,
            policy_decision_id=policy_decision_id,
            event_type="gateway.policy_simulate",
            correlation_id=request.state.request_id,
        )
        observe_query_latency(
            workspace_id=workspace_id,
            engine="policy",
            result=result,
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )
        return {
            "workspace_id": workspace_id,
            "action": str(payload.get("action", "query")),
            "result": result,
            "reason": reason,
            "applied_filters": _serialize_row_filter(abac.row_filter),
            "applied_masks": abac.masks,
            "policy_decision_id": policy_decision_id,
            "request_id": request.state.request_id,
        }

    @app.post("/api/v1/gateway/retrieve")
    async def retrieve(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        effective_policy_pack = _load_effective_policy_pack(
            session_factory=session_factory,
            workspace_id=workspace_id,
        )
        request_context = _request_context(payload)
        actor_dict = authenticated_actor_from_request(
            request,
            settings=settings,
            auth_tokens=auth_tokens,
        )
        policy_decision_id = new_ulid()

        if actor_dict is None:
            reason = "missing_or_invalid_auth_token"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id="unknown",
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        attributes = actor_dict.get("attributes", {})
        attributes_dict = attributes if isinstance(attributes, dict) else {}
        actor_type = str(actor_dict.get("actor_type", "")).lower()
        allowlisted_ai = actor_type == "ai" and bool(attributes_dict.get("ai_allowlisted", False))
        decision: AccessDecision = evaluate_access(actor_dict, allow_ai=allowlisted_ai)
        if decision.result != "allow":
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=decision.reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=decision.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": decision.reason, "policy_decision_id": policy_decision_id},
            )
        actor_id = str(actor_dict.get("actor_id", "unknown"))
        rate_limit_decision = rate_limiter.try_acquire(actor_id)
        if not rate_limit_decision.allowed:
            reason = rate_limit_decision.reason
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=actor_id,
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        allowed_dataset_ids_raw = attributes_dict.get("allowed_dataset_ids", [])
        allowed_dataset_ids = (
            {str(item) for item in allowed_dataset_ids_raw}
            if isinstance(allowed_dataset_ids_raw, list)
            else set()
        )
        if not allowed_dataset_ids:
            reason = "missing_dataset_entitlements"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )
        cross_workspace_dataset_ids = sorted(
            dataset_id
            for dataset_id in allowed_dataset_ids
            if _dataset_belongs_to_other_workspace(
                session_factory=session_factory,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
            )
        )
        if cross_workspace_dataset_ids:
            reason = "dataset_workspace_mismatch"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={
                    "endpoint": "retrieve",
                    "cross_workspace_dataset_ids": cross_workspace_dataset_ids,
                },
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={"reason": reason, "policy_decision_id": policy_decision_id},
            )

        resource_attributes = payload.get("resource_attributes", {})
        resource_attrs = resource_attributes if isinstance(resource_attributes, dict) else {}
        abac_mode = str(payload.get("abac_mode", "internal"))
        abac = evaluate_abac(actor=actor_dict, resource_attributes=resource_attrs, mode=abac_mode)
        if not abac.allow:
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=abac.reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=abac.reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by ABAC",
                details={"reason": abac.reason, "policy_decision_id": policy_decision_id},
            )

        query_text = str(payload.get("query_text", ""))
        try:
            if settings.retrieval_backend == "filesystem":
                corpus = load_retrieval_corpus(
                    storage_root=settings.storage_root,
                    workspace_id=workspace_id,
                )
                results = retrieve_documents(
                    query_text=query_text,
                    corpus=corpus,
                    allowed_dataset_ids=allowed_dataset_ids,
                )
            elif settings.retrieval_backend == "opensearch":
                if not settings.opensearch_enabled:
                    reason = "module_disabled"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={
                            "endpoint": "retrieve",
                            "retrieval_backend": settings.retrieval_backend,
                        },
                        applied_filters={},
                        applied_masks={},
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.retrieve",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="retrieve",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={"reason": reason, "policy_decision_id": policy_decision_id},
                    )
                try:
                    results = search_opensearch_documents(
                        query_text=query_text,
                        workspace_id=workspace_id,
                        allowed_dataset_ids=allowed_dataset_ids,
                        base_url=settings.opensearch_url,
                        index_name=settings.opensearch_index,
                        timeout_ms=settings.opensearch_timeout_ms,
                    )
                except OpenSearchUnavailableError as exc:
                    reason = str(exc).strip() or "retrieval_backend_unavailable"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={
                            "endpoint": "retrieve",
                            "retrieval_backend": settings.retrieval_backend,
                        },
                        applied_filters={},
                        applied_masks={},
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.retrieve",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="retrieve",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={
                            "reason": reason,
                            "policy_decision_id": policy_decision_id,
                        },
                    ) from exc
            elif settings.retrieval_backend == "qdrant":
                if not settings.qdrant_enabled:
                    reason = "module_disabled"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={
                            "endpoint": "retrieve",
                            "retrieval_backend": settings.retrieval_backend,
                        },
                        applied_filters={},
                        applied_masks={},
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.retrieve",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="retrieve",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={"reason": reason, "policy_decision_id": policy_decision_id},
                    )
                try:
                    query_vector = embeddings_provider.embed(query_text)
                    results = search_qdrant_documents(
                        query_vector=query_vector,
                        workspace_id=workspace_id,
                        allowed_dataset_ids=allowed_dataset_ids,
                        base_url=settings.qdrant_url,
                        collection_name=settings.qdrant_collection,
                        timeout_ms=settings.qdrant_timeout_ms,
                    )
                except DisabledIntegrationError as exc:
                    reason = "embedding_provider_disabled"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={
                            "endpoint": "retrieve",
                            "retrieval_backend": settings.retrieval_backend,
                        },
                        applied_filters={},
                        applied_masks={},
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.retrieve",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="retrieve",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={
                            "reason": reason,
                            "policy_decision_id": policy_decision_id,
                            "error": str(exc),
                        },
                    ) from exc
                except QdrantUnavailableError as exc:
                    reason = str(exc).strip() or "retrieval_backend_unavailable"
                    _record_access_decision(
                        session_factory(),
                        workspace_id=workspace_id,
                        actor_id=str(actor_dict.get("actor_id", "unknown")),
                        result="deny",
                        reason=reason,
                        request_context=request_context,
                        resources={
                            "endpoint": "retrieve",
                            "retrieval_backend": settings.retrieval_backend,
                        },
                        applied_filters={},
                        applied_masks={},
                        policy_decision_id=policy_decision_id,
                        event_type="gateway.retrieve",
                        correlation_id=request.state.request_id,
                    )
                    increment_policy_denial(workspace_id=workspace_id, reason=reason)
                    observe_query_latency(
                        workspace_id=workspace_id,
                        engine="retrieve",
                        result="deny",
                        latency_ms=(perf_counter() - started_at) * 1000.0,
                    )
                    raise PolicyDeniedError(
                        "Access denied by policy",
                        details={
                            "reason": reason,
                            "policy_decision_id": policy_decision_id,
                        },
                    ) from exc
            else:
                reason = "retrieval_backend_unsupported"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={
                        "endpoint": "retrieve",
                        "retrieval_backend": settings.retrieval_backend,
                    },
                    applied_filters={},
                    applied_masks={},
                    policy_decision_id=policy_decision_id,
                    event_type="gateway.retrieve",
                    correlation_id=request.state.request_id,
                )
                increment_policy_denial(workspace_id=workspace_id, reason=reason)
                observe_query_latency(
                    workspace_id=workspace_id,
                    engine="retrieve",
                    result="deny",
                    latency_ms=(perf_counter() - started_at) * 1000.0,
                )
                raise PolicyDeniedError(
                    "Access denied by policy",
                    details={"reason": reason, "policy_decision_id": policy_decision_id},
                )
        finally:
            rate_limiter.release(actor_id)

        dataset_summaries = _load_dataset_sensitivity_summaries(
            session_factory=session_factory,
            workspace_id=workspace_id,
            dataset_ids={str(item.get("dataset_id", "")) for item in results},
        )
        results = _apply_retrieval_row_filter(
            results=results,
            row_filter=abac.row_filter,
            dataset_summaries=dataset_summaries,
        )
        results = _apply_retrieval_masks(results=results, masks=abac.masks)
        estimated_retrieval_bytes = estimate_retrieval_cost_bytes(
            query_text=query_text,
            result_count=len(results),
        )
        if not enforce_budget(
            estimated_bytes=estimated_retrieval_bytes,
            budget_bytes=settings.retrieval_max_bytes,
        ):
            reason = "retrieval_budget_exceeded"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={
                    "endpoint": "retrieve",
                    "estimated_retrieval_bytes": estimated_retrieval_bytes,
                    "retrieval_budget_bytes": settings.retrieval_max_bytes,
                },
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                    "estimated_retrieval_bytes": estimated_retrieval_bytes,
                    "retrieval_budget_bytes": settings.retrieval_max_bytes,
                },
            )
        increment_cost_bytes_scanned(
            workspace_id=workspace_id,
            engine="retrieve",
            bytes_scanned=max(len(query_text.encode("utf-8")), 1),
        )
        observe_query_latency(
            workspace_id=workspace_id,
            engine="retrieve",
            result="allow",
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )
        citations = [str(item.get("citation", "")) for item in results if item.get("citation")]
        dataset_ids = sorted({str(item.get("dataset_id", "")) for item in results})
        query_id = new_ulid()
        try:
            provenance = build_provenance_v1(
                workspace_id=workspace_id,
                policy_decision_id=policy_decision_id,
                query_id=query_id,
                build_id=new_ulid(),
                datasets_used=dataset_ids,
                snapshots=[],
                decision_reason="allow",
                applied_filters=_serialize_row_filter(abac.row_filter),
                applied_masks=abac.masks,
                citations=citations,
                allowed_dataset_ids=sorted(allowed_dataset_ids),
                policy_pack=effective_policy_pack,
            )
        except ValueError as exc:
            reason = "provenance_unavailable"
            _record_access_decision(
                session_factory(),
                workspace_id=workspace_id,
                actor_id=str(actor_dict.get("actor_id", "unknown")),
                result="deny",
                reason=reason,
                request_context=request_context,
                resources={"endpoint": "retrieve"},
                applied_filters={},
                applied_masks={},
                policy_decision_id=policy_decision_id,
                event_type="gateway.retrieve",
                correlation_id=request.state.request_id,
            )
            increment_policy_denial(workspace_id=workspace_id, reason=reason)
            observe_query_latency(
                workspace_id=workspace_id,
                engine="retrieve",
                result="deny",
                latency_ms=(perf_counter() - started_at) * 1000.0,
            )
            raise PolicyDeniedError(
                "Access denied by policy",
                details={
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                    "error": str(exc),
                },
            ) from exc
        _record_access_decision(
            session_factory(),
            workspace_id=workspace_id,
            actor_id=str(actor_dict.get("actor_id", "unknown")),
            result="allow",
            reason="allow",
            request_context=request_context,
            resources={
                "endpoint": "retrieve",
                "query_text": query_text,
                "allowed_dataset_ids": sorted(allowed_dataset_ids),
                "datasets_used": dataset_ids,
                "retrieval_backend": settings.retrieval_backend,
                "policy_pack": effective_policy_pack,
            },
            applied_filters=_serialize_row_filter(abac.row_filter),
            applied_masks=abac.masks,
            policy_decision_id=policy_decision_id,
            event_type="gateway.retrieve",
            correlation_id=request.state.request_id,
        )
        return {
            "results": results,
            "provenance": provenance,
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    return app


def _request_context(payload: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in payload.items() if k not in {"actor", "corpus"}}


def _build_query_cache_key(
    *,
    workspace_id: str,
    actor_id: str,
    actor_roles: object,
    actor_attributes: dict[str, object],
    query_text: str,
    datasets_used: list[str],
    row_filter: tuple[str, str] | None,
    masks: Mapping[str, object],
    max_rows: int,
    timeout_ms: int,
    query_engine: str,
    policy_pack: dict[str, object] | None,
    storage_root: str,
) -> str:
    pointer = load_latest_gold_pointer(workspace_id=workspace_id, storage_root=storage_root) or {}
    payload = {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "actor_roles": list(actor_roles) if isinstance(actor_roles, list) else [],
        "actor_attributes": actor_attributes,
        "query_text": query_text,
        "datasets_used": sorted(str(item) for item in datasets_used),
        "row_filter": _serialize_row_filter(row_filter),
        "masks": dict(masks),
        "max_rows": max_rows,
        "timeout_ms": timeout_ms,
        "query_engine": query_engine,
        "policy_pack": policy_pack or {},
        "snapshot_id": str(pointer.get("snapshot_id", "")),
        "build_id": str(pointer.get("build_id", "")),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _serialize_row_filter(row_filter: tuple[str, str] | None) -> dict[str, object]:
    if row_filter is None:
        return {}
    return {"row_filter": {"column": row_filter[0], "value": row_filter[1]}}


EMAIL_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _load_dataset_sensitivity_summaries(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
    dataset_ids: set[str],
) -> dict[str, dict[str, object]]:
    if not dataset_ids:
        return {}
    session = session_factory()
    try:
        rows = session.execute(
            select(CatalogDataset.dataset_id, CatalogDataset.sensitivity_summary_json).where(
                CatalogDataset.workspace_id == workspace_id,
                CatalogDataset.dataset_id.in_(sorted(dataset_ids)),
            )
        ).all()
    finally:
        session.close()
    summaries: dict[str, dict[str, object]] = {}
    for dataset_id, summary in rows:
        if isinstance(summary, dict):
            summaries[str(dataset_id)] = summary
    return summaries


def _apply_retrieval_row_filter(
    *,
    results: list[dict[str, object]],
    row_filter: tuple[str, str] | None,
    dataset_summaries: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if row_filter is None:
        return results
    filter_key, filter_value = row_filter
    filtered: list[dict[str, object]] = []
    for row in results:
        dataset_id = str(row.get("dataset_id", ""))
        summary = dataset_summaries.get(dataset_id, {})
        candidate = summary.get(filter_key)
        if candidate is None:
            continue
        if str(candidate) == filter_value:
            filtered.append(row)
    return filtered


def _apply_retrieval_masks(
    *, results: list[dict[str, object]], masks: Mapping[str, object]
) -> list[dict[str, object]]:
    if not masks:
        return results
    masked: list[dict[str, object]] = []
    email_mask_mode_raw = masks.get("email")
    email_mask_mode = str(email_mask_mode_raw) if email_mask_mode_raw else ""
    snippet_mask_mode_raw = masks.get("snippet")
    snippet_mask_mode = str(snippet_mask_mode_raw) if snippet_mask_mode_raw else ""
    for row in results:
        updated = dict(row)
        snippet = str(updated.get("snippet", ""))
        if snippet and email_mask_mode:
            snippet = _mask_email_tokens(text=snippet, mode=email_mask_mode)
        if snippet and snippet_mask_mode:
            snippet = str(apply_mask(snippet, snippet_mask_mode))
        updated["snippet"] = snippet
        masked.append(updated)
    return masked


def _mask_email_tokens(*, text: str, mode: str) -> str:
    return EMAIL_TOKEN_PATTERN.sub(lambda match: str(apply_mask(match.group(0), mode)), text)


def _record_access_decision(
    session: Session,
    *,
    workspace_id: str,
    actor_id: str,
    result: str,
    reason: str,
    request_context: dict[str, object],
    resources: dict[str, object],
    applied_filters: Mapping[str, object],
    applied_masks: Mapping[str, object],
    policy_decision_id: str,
    event_type: str,
    correlation_id: str,
) -> None:
    """Write append-only audit and access-decision rows."""
    event = AuditEvent(
        audit_event_id=new_ulid(),
        workspace_id=workspace_id,
        actor_id=actor_id,
        event_type=event_type,
        event_json={"reason": reason},
        correlation_id=correlation_id,
    )
    try:
        session.add(event)
        decision = AccessDecisionRow(
            decision_id=policy_decision_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            request_context_json=request_context,
            resources_json=resources,
            result=result,
            applied_filters_json=dict(applied_filters),
            applied_masks_json=dict(applied_masks),
            audit_event_id=event.audit_event_id,
        )
        session.add(decision)
        payload: dict[str, object] = {
            "audit_event_id": event.audit_event_id,
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            "event_type": event_type,
            "event_json": event.event_json,
            "correlation_id": correlation_id,
            "decision_id": policy_decision_id,
            "result": result,
            "reason": reason,
        }
        if _AUDIT_SINK_MODE == "inline":
            _ACTIVE_AUDIT_SINK.emit(payload)
        else:
            enqueue_audit_outbox_event(
                session,
                service="gateway",
                workspace_id=workspace_id,
                audit_event_id=event.audit_event_id,
                payload=payload,
            )
        session.commit()
    except AuditSinkError as exc:
        session.rollback()
        increment_audit_write_failure(
            workspace_id=workspace_id,
            service="gateway",
            operation=f"{event_type}:audit_sink",
        )
        log_structured_event(
            level="error",
            msg="audit.sink_failed",
            service="gateway",
            correlation_id=correlation_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type="audit.sink_failed",
            extra={"operation": event_type, "error": str(exc)},
        )
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "audit_sink_unavailable", "operation": event_type},
        ) from exc
    except Exception as exc:
        session.rollback()
        increment_audit_write_failure(
            workspace_id=workspace_id,
            service="gateway",
            operation=event_type,
        )
        log_structured_event(
            level="error",
            msg="audit.write_failed",
            service="gateway",
            correlation_id=correlation_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type="audit.write_failed",
            extra={"operation": event_type, "error": str(exc)},
        )
        raise PolicyDeniedError(
            "Access denied by policy",
            details={"reason": "audit_unavailable", "operation": event_type},
        ) from exc
    finally:
        session.close()


def _dataset_belongs_to_other_workspace(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
    dataset_id: str,
) -> bool:
    session = session_factory()
    try:
        row = session.execute(
            select(CatalogDataset.workspace_id).where(CatalogDataset.dataset_id == dataset_id)
        ).scalar_one_or_none()
    finally:
        session.close()
    if row is None:
        return False
    return str(row) != workspace_id


def _load_effective_policy_pack(
    *,
    session_factory: Callable[[], Session],
    workspace_id: str,
) -> dict[str, object] | None:
    session = session_factory()
    try:
        row = (
            session.execute(
                select(GovernancePolicy).where(
                    GovernancePolicy.workspace_id == workspace_id,
                    GovernancePolicy.policy_type == "policy_pack",
                    GovernancePolicy.status == "active",
                )
            )
            .scalars()
            .first()
        )
    finally:
        session.close()
    if row is None:
        return None
    try:
        payload = json.loads(row.definition_ref)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    pack_id = str(payload.get("pack_id", "")).strip()
    version_raw = payload.get("version", 0)
    version = int(version_raw) if isinstance(version_raw, (int, float, str)) else 0
    if not pack_id:
        return None
    return {"pack_id": pack_id, "version": version}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default
