"""Control-plane FastAPI application."""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.control_plane import db_models
from backend.control_plane.decision_engine import build_recommendation_report
from backend.control_plane.deletion import DeletionRequest, execute_deletion_workflow
from backend.control_plane.gating import evaluate_gold_publish_gate
from backend.control_plane.repository import (
    append_audit_event,
    create_run,
    create_source,
    create_workspace,
    get_dataset,
    get_run,
    get_workspace,
    list_datasets,
    list_sources,
    list_workspaces,
    update_source,
)
from backend.control_plane.review_repository import (
    create_proposal,
    create_review_task,
    decide_review_task,
    get_review_queue_summary,
    list_review_tasks,
    unresolved_blocking_task_count,
)
from backend.control_plane.schemas import (
    ErrorInner,
    ErrorResponse,
    RecommendationCreateRequest,
    RunCreateRequest,
    SourceCreateRequest,
    WorkspaceCreateRequest,
)
from backend.shared_domain.config import Settings, load_settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.errors import SchemaPilotError
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.observability import (
    increment_contract_failure,
    log_structured_event,
    render_metrics,
    set_review_queue_backlog,
)
from backend.shared_domain.policy_packs import list_policy_pack_summaries


def create_app(settings_factory: Callable[[], Settings] = load_settings) -> FastAPI:
    """Create control-plane application instance."""
    settings = settings_factory()
    settings.validate()
    if settings.database_url.startswith("sqlite:///"):
        sqlite_path = settings.database_url.removeprefix("sqlite:///")
        db_file = Path(sqlite_path)
        if db_file.parent.as_posix() != ".":
            db_file.parent.mkdir(parents=True, exist_ok=True)
    session_factory = get_session_factory(settings.database_url)
    db_models.Base.metadata.create_all(bind=get_engine(settings.database_url))
    app = FastAPI(title="SchemaPilot Control Plane", version="0.1.0")

    def get_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id", new_ulid())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        log_structured_event(
            level="info",
            msg="request.completed",
            service="control_plane",
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
        payload = ErrorResponse(
            error=ErrorInner(
                code=exc.error_code, message=str(exc), details=exc.details, request_id=request_id
            )
        )
        status_code = 404 if exc.error_code == "NOT_FOUND" else 400
        return JSONResponse(status_code=status_code, content=payload.model_dump())

    def not_found_response(
        *, request: Request, message: str, details: dict[str, object]
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_ulid())
        payload = ErrorResponse(
            error=ErrorInner(
                code="NOT_FOUND",
                message=message,
                details=details,
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=404, content=payload.model_dump())

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "control_plane",
            "profile": settings.profile,
            "bind_address": settings.bind_address,
        }

    @app.get("/api/v1/metrics")
    async def metrics() -> Response:
        payload, media_type = render_metrics()
        return Response(content=payload, media_type=media_type)

    @app.get("/api/v1/policy-packs")
    async def api_list_policy_packs() -> list[dict[str, str]]:
        return list_policy_pack_summaries()

    @app.get("/api/v1/workspaces")
    async def api_list_workspaces(
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        return list_workspaces(session)

    @app.post("/api/v1/workspaces")
    async def api_create_workspace(
        payload: WorkspaceCreateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        workspace = create_workspace(
            session,
            name=payload.name,
            profile=payload.profile,
            security_baseline=payload.security_baseline,
        )
        append_audit_event(
            session,
            workspace_id=str(workspace["workspace_id"]),
            actor_id="system",
            event_type="workspace.created",
            event_json=workspace,
            correlation_id=request.state.request_id,
        )
        return workspace

    @app.get("/api/v1/workspaces/{workspace_id}")
    async def api_get_workspace(
        workspace_id: str, request: Request, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        workspace = get_workspace(session, workspace_id)
        if workspace is None:
            return not_found_response(
                request=request,
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )  # type: ignore[return-value]
        return workspace

    @app.post("/api/v1/workspaces/{workspace_id}/sources")
    async def api_create_source(
        workspace_id: str,
        payload: SourceCreateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        source = create_source(
            session,
            workspace_id=workspace_id,
            source_type=payload.source_type,
            scope=payload.scope,
            display_name=payload.display_name,
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id="system",
            event_type="source.created",
            event_json=source,
            correlation_id=request.state.request_id,
        )
        return source

    @app.get("/api/v1/workspaces/{workspace_id}/sources")
    async def api_list_sources(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> list[dict[str, object]]:
        return list_sources(session, workspace_id)

    @app.patch("/api/v1/workspaces/{workspace_id}/sources/{source_id}")
    async def api_update_source(
        workspace_id: str,
        source_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        source = update_source(
            session,
            workspace_id=workspace_id,
            source_id=source_id,
            patch=payload,
        )
        if source is None:
            return not_found_response(
                request=request,
                message="Source not found.",
                details={"workspace_id": workspace_id, "source_id": source_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id="system",
            event_type="source.updated",
            event_json=source,
            correlation_id=request.state.request_id,
        )
        return source

    @app.get("/api/v1/workspaces/{workspace_id}/datasets")
    async def api_list_datasets(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> list[dict[str, object]]:
        return list_datasets(session, workspace_id)

    @app.get("/api/v1/workspaces/{workspace_id}/datasets/{dataset_id}")
    async def api_get_dataset(
        workspace_id: str,
        dataset_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        dataset = get_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
        if dataset is not None:
            return dataset
        return not_found_response(
            request=request,
            message="Dataset not found.",
            details={"workspace_id": workspace_id, "dataset_id": dataset_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/runs")
    async def api_create_run(
        workspace_id: str,
        payload: RunCreateRequest,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        run = create_run(session, workspace_id=workspace_id, run_type=payload.run_type)
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id="system",
            event_type="run.created",
            event_json=run,
            correlation_id=request.state.request_id,
        )
        return run

    @app.get("/api/v1/workspaces/{workspace_id}/runs/{run_id}")
    async def api_get_run(
        workspace_id: str,
        run_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        run = get_run(session, workspace_id=workspace_id, run_id=run_id)
        if run is None:
            return not_found_response(
                request=request,
                message="Run not found.",
                details={"workspace_id": workspace_id, "run_id": run_id},
            )  # type: ignore[return-value]
        return run

    @app.get("/api/v1/workspaces/{workspace_id}/review_tasks")
    async def api_list_review_tasks(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> list[dict[str, object]]:
        tasks = list_review_tasks(session, workspace_id)
        backlog: dict[str, int] = {}
        for task in tasks:
            priority = str(task.get("priority", "unknown"))
            backlog[priority] = backlog.get(priority, 0) + 1
        for priority, count in backlog.items():
            set_review_queue_backlog(workspace_id=workspace_id, priority=priority, count=count)
        return tasks

    @app.get("/api/v1/workspaces/{workspace_id}/review_tasks/summary")
    async def api_review_queue_summary(
        workspace_id: str, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        summary = get_review_queue_summary(session, workspace_id)
        by_priority_raw = summary.get("by_priority", {})
        if isinstance(by_priority_raw, dict):
            for priority, count in by_priority_raw.items():
                set_review_queue_backlog(
                    workspace_id=workspace_id,
                    priority=str(priority),
                    count=int(count),
                )
        return summary

    @app.post("/api/v1/onboarding/demo_bootstrap")
    async def api_demo_bootstrap(
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        workspace = create_workspace(
            session,
            name=str(payload.get("workspace_name", "Demo Workspace")),
            profile=str(payload.get("profile", "starter")),
            security_baseline=str(payload.get("security_baseline", "standard")),
        )
        demo_root = Path(settings.storage_root).parent / "demo_data"
        demo_root.mkdir(parents=True, exist_ok=True)
        demo_csv = demo_root / "invoices_demo.csv"
        if not demo_csv.exists():
            demo_csv.write_text(
                "invoice_id,customer,region,amount,email\n"
                "1001,ACME,eu,1200.5,alice@acme.example\n"
                "1002,Beta,us,900.0,bob@beta.example\n",
                encoding="utf-8",
            )
        source = create_source(
            session,
            workspace_id=str(workspace["workspace_id"]),
            source_type="filesystem",
            scope={"root_path": demo_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Demo Files",
        )
        run = create_run(
            session,
            workspace_id=str(workspace["workspace_id"]),
            run_type="discover",
        )
        proposal = create_proposal(
            session,
            workspace_id=str(workspace["workspace_id"]),
            proposal_type="pii_tag_proposal",
            evidence_bundle_uri="evidence://demo/onboarding/pii",
            confidence=0.68,
        )
        review_task = create_review_task(
            session,
            workspace_id=str(workspace["workspace_id"]),
            subject_ref=str(proposal["proposal_id"]),
            priority="security_critical",
            blocking=True,
        )
        response_payload: dict[str, object] = {
            "workspace": workspace,
            "source": source,
            "run": run,
            "review_task": review_task,
            "demo_data_path": demo_root.as_posix(),
            "first_query_example": {
                "endpoint": "/api/v1/gateway/query",
                "authorization": "Bearer local-analyst-token",
                "payload": {
                    "workspace_id": str(workspace["workspace_id"]),
                    "query": {"language": "sql", "text": "select 1 as one"},
                    "resource_attributes": {"dataset_id": "dataset-1"},
                },
            },
            "next_steps": [
                "Review and approve the demo review task.",
                "Run a governed query through the gateway.",
                "Generate a recommendation report for your workspace.",
            ],
        }
        append_audit_event(
            session,
            workspace_id=str(workspace["workspace_id"]),
            actor_id="system",
            event_type="onboarding.demo_bootstrap",
            event_json=response_payload,
            correlation_id=request.state.request_id,
        )
        return response_payload

    @app.post("/api/v1/workspaces/{workspace_id}/proposals")
    async def api_create_proposal(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        confidence_raw = payload.get("confidence", 0.5)
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float, str)) else 0.5
        proposal = create_proposal(
            session,
            workspace_id=workspace_id,
            proposal_type=str(payload.get("proposal_type", "schema_proposal")),
            evidence_bundle_uri=str(payload.get("evidence_bundle_uri", "evidence://stub")),
            confidence=confidence,
        )
        task = create_review_task(
            session,
            workspace_id=workspace_id,
            subject_ref=str(proposal["proposal_id"]),
            priority=str(payload.get("priority", "quality_critical")),
            blocking=bool(payload.get("blocking", False)),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id="system",
            event_type="proposal.created",
            event_json={"proposal": proposal, "task": task},
            correlation_id=request.state.request_id,
        )
        return {"proposal": proposal, "task": task}

    @app.post("/api/v1/workspaces/{workspace_id}/review_tasks/{task_id}/decision")
    async def api_decide_review_task(
        workspace_id: str,
        task_id: str,
        payload: dict[str, str],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        decision = decide_review_task(
            session,
            workspace_id=workspace_id,
            task_id=task_id,
            actor_id=str(payload.get("actor_id", "unknown")),
            decision=str(payload.get("decision", "defer")),
            reason=str(payload.get("decision_reason", "")),
        )
        if decision is None:
            return not_found_response(
                request=request,
                message="Review task not found.",
                details={"workspace_id": workspace_id, "task_id": task_id},
            )  # type: ignore[return-value]
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(payload.get("actor_id", "unknown")),
            event_type="review.decision",
            event_json=decision,
            correlation_id=request.state.request_id,
        )
        return decision

    @app.post("/api/v1/workspaces/{workspace_id}/recommendations")
    async def api_create_recommendation(
        workspace_id: str, payload: RecommendationCreateRequest
    ) -> dict[str, object]:
        report = build_recommendation_report(payload.intent)
        return {
            "report_id": new_ulid(),
            "workspace_id": workspace_id,
            "ranked_templates": report["ranked_templates"],
            "hard_constraint_gates": report["hard_constraint_gates"],
            "confidence": report["confidence"],
            "missing_evidence": report["missing_evidence"],
            "approval_required": report["approval_required"],
            "approval_reasons": report["approval_reasons"],
            "intent": payload.intent,
        }

    @app.get("/api/v1/workspaces/{workspace_id}/recommendations/{report_id}")
    async def api_get_recommendation(
        workspace_id: str, report_id: str, request: Request
    ) -> dict[str, object]:
        _ = report_id
        return not_found_response(
            request=request,
            message="Recommendation report not found.",
            details={"workspace_id": workspace_id, "report_id": report_id},
        )  # type: ignore[return-value]

    @app.post("/api/v1/workspaces/{workspace_id}/builds/{build_id}/publish")
    async def api_publish_build(
        workspace_id: str,
        build_id: str,
        request: Request,
        payload: dict[str, object],
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        gate = evaluate_gold_publish_gate(
            contracts_passed=bool(payload.get("contracts_passed", True)),
            unresolved_blocking_tasks=unresolved_blocking_task_count(session, workspace_id),
        )
        result_payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "build_id": build_id,
            "status": "published_stub" if gate["allowed"] else "blocked",
            "gate_reason": gate["reason"],
        }
        if not gate["allowed"] and gate["reason"] == "contract_failure":
            increment_contract_failure(workspace_id=workspace_id, layer="gold")
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id="system",
            event_type="build.published",
            event_json=result_payload,
            correlation_id=request.state.request_id,
        )
        return result_payload

    @app.post("/api/v1/workspaces/{workspace_id}/builds/{build_id}/rollback")
    async def api_rollback_build(
        workspace_id: str,
        build_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "workspace_id": workspace_id,
            "build_id": build_id,
            "status": "rolled_back_stub",
        }
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id="system",
            event_type="build.rollback",
            event_json=payload,
            correlation_id=request.state.request_id,
        )
        return payload

    @app.post("/api/v1/workspaces/{workspace_id}/deletions")
    async def api_execute_deletion(
        workspace_id: str,
        payload: dict[str, object],
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        subject_selector_raw = payload.get("subject_selector", {})
        subject_selector: dict[str, object] = (
            subject_selector_raw if isinstance(subject_selector_raw, dict) else {}
        )
        affected_snapshots_raw = payload.get("affected_snapshots", [])
        affected_snapshots = (
            [str(item) for item in affected_snapshots_raw if isinstance(item, (str, int, float))]
            if isinstance(affected_snapshots_raw, list)
            else []
        )
        affected_indexes_raw = payload.get("affected_indexes", [])
        affected_indexes = (
            [str(item) for item in affected_indexes_raw if isinstance(item, (str, int, float))]
            if isinstance(affected_indexes_raw, list)
            else []
        )
        request_obj = DeletionRequest(
            workspace_id=workspace_id,
            subject_selector=subject_selector,
            legal_hold_active=bool(payload.get("legal_hold_active", False)),
            approved=bool(payload.get("approved", False)),
            affected_snapshots=affected_snapshots,
            affected_indexes=affected_indexes,
            backup_reference=(
                str(payload.get("backup_reference"))
                if payload.get("backup_reference") is not None
                else None
            ),
        )
        result = execute_deletion_workflow(
            request_obj,
            output_root=str(payload.get("output_root", "./runtime")),
        )
        append_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=str(payload.get("actor_id", "system")),
            event_type="deletion.workflow",
            event_json=result,
            correlation_id=request.state.request_id,
        )
        return result

    return app
