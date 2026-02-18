"""Query gateway FastAPI application."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from copy import deepcopy
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.gateway.abac import apply_mask, evaluate_abac
from backend.gateway.executor import QueryTimeoutError, UnsafeSqlError, execute_sql
from backend.gateway.policy import AccessDecision, evaluate_access
from backend.shared_domain.audit_models import AccessDecision as AccessDecisionRow
from backend.shared_domain.audit_models import AuditEvent
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.db import Base, get_engine, get_session_factory
from backend.shared_domain.errors import PolicyDeniedError, SchemaPilotError
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.observability import (
    increment_cost_bytes_scanned,
    increment_policy_denial,
    log_structured_event,
    observe_query_latency,
    render_metrics,
)
from backend.shared_domain.policy_packs import find_policy_pack_template
from backend.shared_domain.retrieval import load_retrieval_corpus, retrieve_documents

DEFAULT_LOCAL_AUTH_TOKENS: dict[str, dict[str, object]] = {
    "local-analyst-token": {
        "actor_id": "user:local_analyst",
        "actor_type": "human",
        "roles": ["analyst"],
        "attributes": {},
    },
    "local-region-analyst-token": {
        "actor_id": "user:regional_analyst",
        "actor_type": "human",
        "roles": ["analyst"],
        "attributes": {"region": "eu"},
    },
    "local-data-steward-token": {
        "actor_id": "user:local_steward",
        "actor_type": "human",
        "roles": ["data_steward"],
        "attributes": {},
    },
    "local-platform-admin-token": {
        "actor_id": "user:local_admin",
        "actor_type": "human",
        "roles": ["platform_admin"],
        "attributes": {},
    },
    "local-ai-token": {
        "actor_id": "agent:local_ai",
        "actor_type": "ai",
        "roles": ["ai_agent"],
        "attributes": {"ai_allowlisted": False, "allowed_dataset_ids": []},
    },
    "local-ai-reader-token": {
        "actor_id": "agent:local_ai_reader",
        "actor_type": "ai",
        "roles": ["ai_agent"],
        "attributes": {"ai_allowlisted": True, "allowed_dataset_ids": ["dataset-1"]},
    },
}


def create_gateway_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create gateway app with deny-by-default behavior."""
    settings = settings_factory()
    settings.validate()
    session_factory = get_session_factory(settings.database_url)
    Base.metadata.create_all(bind=get_engine(settings.database_url))
    auth_tokens = _load_local_auth_tokens()
    app = FastAPI(title="SchemaPilot Gateway", version="0.1.0")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id", new_ulid())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
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
        request_context = _request_context(payload)
        actor_dict = _authenticated_actor_from_request(
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

        resource_attributes = payload.get("resource_attributes", {})
        resource_attrs = resource_attributes if isinstance(resource_attributes, dict) else {}
        if str(actor_dict.get("actor_type", "human")) == "ai":
            dataset_id = str(resource_attrs.get("dataset_id", "")).strip()
            if not dataset_id:
                reason = "missing_dataset_context"
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
            allowed_raw = actor_attributes.get("allowed_dataset_ids", [])
            allowed = (
                {str(item) for item in allowed_raw} if isinstance(allowed_raw, list) else set()
            )
            if dataset_id not in allowed:
                reason = "dataset_not_allowed"
                _record_access_decision(
                    session_factory(),
                    workspace_id=workspace_id,
                    actor_id=str(actor_dict.get("actor_id", "unknown")),
                    result="deny",
                    reason=reason,
                    request_context=request_context,
                    resources={"endpoint": "query", "dataset_id": dataset_id},
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

        query_payload = payload.get("query", {})
        query_text = ""
        if isinstance(query_payload, dict):
            query_text = str(query_payload.get("text", ""))
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

        try:
            result_set = execute_sql(
                query_text or "select 1 as one",
                max_rows=max_rows,
                row_filter=abac.row_filter,
                timeout_ms=timeout_ms,
                workspace_id=workspace_id,
                storage_root=settings.storage_root,
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
            reason = "abac_filter_not_enforceable" if abac.row_filter is not None else "query_error"
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

        increment_cost_bytes_scanned(
            workspace_id=workspace_id,
            engine="sql",
            bytes_scanned=max(len(query_text.encode("utf-8")), 1),
        )
        masked_rows = []
        column_names = [column["name"] for column in result_set.columns]
        for row in result_set.rows:
            masked_row = []
            for idx, value in enumerate(row):
                column_name = str(column_names[idx]) if idx < len(column_names) else f"col_{idx}"
                mask_mode = abac.masks.get(column_name)
                masked_row.append(apply_mask(value, mask_mode) if mask_mode else value)
            masked_rows.append(masked_row)

        datasets_used = []
        dataset_ref = resource_attrs.get("dataset_id")
        if dataset_ref is not None:
            datasets_used.append(str(dataset_ref))

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

        return {
            "result": {
                "columns": result_set.columns,
                "rows": masked_rows,
                "row_count": len(masked_rows),
            },
            "provenance": {
                "datasets_used": datasets_used,
                "policy_decision_id": policy_decision_id,
                "build_id": new_ulid(),
                "decision_reason": "allow",
                "applied_filters": _serialize_row_filter(abac.row_filter),
                "applied_masks": abac.masks,
            },
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    @app.post("/api/v1/gateway/retrieve")
    async def retrieve(payload: dict[str, object], request: Request) -> dict[str, object]:
        started_at = perf_counter()
        workspace_id = str(payload.get("workspace_id", "unknown"))
        request_context = _request_context(payload)
        actor_dict = _authenticated_actor_from_request(
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

        corpus = load_retrieval_corpus(
            storage_root=settings.storage_root,
            workspace_id=workspace_id,
        )
        query_text = str(payload.get("query_text", ""))
        results = retrieve_documents(
            query_text=query_text,
            corpus=corpus,
            allowed_dataset_ids=allowed_dataset_ids,
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
            },
            applied_filters={},
            applied_masks={},
            policy_decision_id=policy_decision_id,
            event_type="gateway.retrieve",
            correlation_id=request.state.request_id,
        )
        return {
            "results": results,
            "provenance": {
                "policy_decision_id": policy_decision_id,
                "datasets_used": dataset_ids,
                "citations": citations,
                "decision_reason": "allow",
                "allowed_dataset_ids": sorted(allowed_dataset_ids),
            },
            "audit_event_id": new_ulid(),
            "request_id": request.state.request_id,
        }

    return app


def _load_local_auth_tokens() -> dict[str, dict[str, object]]:
    raw = os.getenv("SCHEMAPILOT_LOCAL_AUTH_TOKENS")
    if raw is None:
        return deepcopy(DEFAULT_LOCAL_AUTH_TOKENS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    tokens: dict[str, dict[str, object]] = {}
    for token, actor in parsed.items():
        if not isinstance(token, str) or not isinstance(actor, dict):
            continue
        roles_raw = actor.get("roles", [])
        roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
        attributes_raw = actor.get("attributes", {})
        attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
        tokens[token] = {
            "actor_id": str(actor.get("actor_id", "unknown")),
            "actor_type": str(actor.get("actor_type", "human")),
            "roles": roles,
            "attributes": attributes,
        }
    _apply_policy_pack_overrides(tokens)
    return tokens


def _apply_policy_pack_overrides(tokens: dict[str, dict[str, object]]) -> None:
    raw = os.getenv("SCHEMAPILOT_LOCAL_AUTH_PACKS")
    if raw is None:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(parsed, dict):
        return
    for token, pack_id in parsed.items():
        if not isinstance(token, str) or not isinstance(pack_id, str):
            continue
        template = find_policy_pack_template(pack_id)
        if template is None:
            continue
        current = tokens.get(token, {"actor_id": f"user:{token}"})
        roles_raw = template.get("roles", [])
        roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
        attributes_raw = template.get("attributes", {})
        attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
        current["actor_type"] = str(template.get("actor_type", current.get("actor_type", "human")))
        current["roles"] = roles
        current["attributes"] = attributes
        tokens[token] = current


def _authenticated_actor_from_request(
    request: Request,
    *,
    settings: Settings,
    auth_tokens: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    auth_mode = settings.auth_mode.lower()
    if auth_mode == "oidc":
        return _authenticated_actor_from_oidc_claims(request, settings=settings)
    authorization = request.headers.get("authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    actor = auth_tokens.get(token)
    if actor is None:
        return None
    return deepcopy(actor)


def _authenticated_actor_from_oidc_claims(
    request: Request, *, settings: Settings
) -> dict[str, object] | None:
    claims_header = request.headers.get(settings.oidc_claims_header, "")
    if not claims_header:
        return None
    try:
        claims = json.loads(claims_header)
    except json.JSONDecodeError:
        return None
    if not isinstance(claims, dict):
        return None
    if settings.oidc_required_issuer:
        issuer = str(claims.get("iss", ""))
        if issuer != settings.oidc_required_issuer:
            return None
    if settings.oidc_required_audience:
        audience_claim = claims.get("aud")
        allowed = False
        if isinstance(audience_claim, str):
            allowed = audience_claim == settings.oidc_required_audience
        elif isinstance(audience_claim, list):
            allowed = settings.oidc_required_audience in {str(item) for item in audience_claim}
        if not allowed:
            return None
    actor_id = str(claims.get(settings.oidc_actor_id_claim, "")).strip()
    if not actor_id:
        return None
    roles_raw = claims.get(settings.oidc_roles_claim, [])
    roles = [str(item) for item in roles_raw] if isinstance(roles_raw, list) else []
    if not roles:
        role_text = str(roles_raw) if roles_raw else ""
        roles = [role_text] if role_text else []
    attributes_raw = claims.get(settings.oidc_attributes_claim, {})
    attributes = attributes_raw if isinstance(attributes_raw, dict) else {}
    return {
        "actor_id": actor_id,
        "actor_type": str(claims.get("actor_type", "human")),
        "roles": roles,
        "attributes": attributes,
    }


def _request_context(payload: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in payload.items() if k not in {"actor", "corpus"}}


def _serialize_row_filter(row_filter: tuple[str, str] | None) -> dict[str, object]:
    if row_filter is None:
        return {}
    return {"row_filter": {"column": row_filter[0], "value": row_filter[1]}}


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
    session.commit()
    session.close()
