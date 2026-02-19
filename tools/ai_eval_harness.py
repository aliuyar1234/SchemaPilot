#!/usr/bin/env python3
"""Deterministic AI eval harness for SQL agent and retrieval flows."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import backend.ai_service.app as ai_service_app
from backend.ai_service.app import create_ai_service_app
from backend.ai_service.eval_runner import evaluate_regression_cases, load_regression_cases
from backend.control_plane.repository import create_workspace
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import Base, GovernancePolicy


def _settings(output_root: Path) -> Settings:
    db_path = output_root / "ai_eval.db"
    storage_root = output_root / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=storage_root.as_posix(),
        database_url=f"sqlite:///{db_path.as_posix()}",
        ai_service_enabled=True,
        ai_provider="mock",
    )


def _seed_semantic_manifest(session: Session, *, workspace_id: str) -> None:
    semantic_manifest = {
        "workspace_id": workspace_id,
        "manifest_version": "1.0.0",
        "entities": [{"entity_id": "invoice", "dataset_id": "dataset-1"}],
        "dimensions": [{"dimension_id": "region", "entity_id": "invoice"}],
        "metrics": [
            {"metric_id": "invoice_count", "entity_id": "invoice", "expression": "count(*)"}
        ],
        "joins": [],
    }
    session.add(
        GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type="semantic_manifest",
            definition_ref=json.dumps({"semantic_manifest": semantic_manifest}, sort_keys=True),
            status="active",
        )
    )
    session.flush()


def run_ai_eval_harness(
    *,
    output_root: Path,
    smoke: bool,
    regression: bool = False,
    cases_root: Path | None = None,
    baseline_path: Path | None = None,
) -> dict[str, object]:
    """Execute deterministic AI eval probes and return report payload."""
    settings = _settings(output_root)
    engine = get_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(settings.database_url)
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="AI Eval Workspace",
            profile="starter",
            security_baseline="standard",
        )
        workspace_id = str(workspace["workspace_id"])
        _seed_semantic_manifest(session, workspace_id=workspace_id)
        session.commit()

    def fake_request_json(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
        gateway_base_url: str | None = None,
        control_plane_base_url: str | None = None,
    ) -> dict[str, object]:
        _ = (
            method,
            payload,
            bearer_token,
            gateway_base_url,
            control_plane_base_url,
        )
        if url.endswith("/api/v1/gateway/query"):
            query_id = "01HAIEVALQUERY0000000000000"
            build_id = "build_ai_eval_1"
            return {
                "result": {"rows": [{"invoice_count": 2}]},
                "provenance": {
                    "provenance_version": "1",
                    "workspace_id": workspace_id,
                    "policy_decision_id": "01HAIEVALPOLICY00000000000",
                    "query_id": query_id,
                    "build_id": build_id,
                    "datasets_used": ["dataset-1"],
                    "citations": [f"sp://query/{query_id}/dataset/dataset-1/build/{build_id}"],
                },
            }
        if url.endswith("/api/v1/gateway/retrieve"):
            return {
                "results": [
                    {
                        "dataset_id": "dataset-1",
                        "snippet": "Invoice 1001 approved",
                        "citation": "doc://invoice/1001",
                    }
                ],
                "provenance": {
                    "provenance_version": "1",
                    "workspace_id": workspace_id,
                    "policy_decision_id": "01HAIEVALRETPOLICY000000000",
                    "query_id": "01HAIEVALRETRIEVE0000000000",
                    "build_id": "build_ai_eval_retrieve_1",
                    "datasets_used": ["dataset-1"],
                    "allowed_dataset_ids": ["dataset-1"],
                    "citations": ["doc://invoice/1001"],
                },
            }
        if url.endswith(f"/api/v1/workspaces/{workspace_id}/datasets"):
            return {"datasets": [{"dataset_id": "dataset-1", "logical_name": "invoices"}]}
        if url.endswith("/api/v1/gateway/policy/simulate"):
            return {
                "workspace_id": workspace_id,
                "result": "allow",
                "reason": "allow",
                "applied_masks": {},
                "applied_filters": {},
            }
        return {}

    original_request_json = ai_service_app.request_json
    ai_service_app.request_json = fake_request_json
    try:
        client = TestClient(create_ai_service_app(settings_factory=lambda: settings))
        headers = {"Authorization": "Bearer local-ai-reader-token"}
        ask_sql = client.post(
            "/api/v1/ai/ask-sql",
            headers=headers,
            json={"workspace_id": workspace_id, "question": "what is invoice_count?"},
        )
        metric_answer = client.post(
            "/api/v1/ai/metric-answer",
            headers=headers,
            json={
                "workspace_id": workspace_id,
                "metric_id": "invoice_count",
                "question": "invoice_count by region",
                "group_by": ["region"],
            },
        )
        doc_qa = client.post(
            "/api/v1/ai/doc-qa",
            headers=headers,
            json={
                "workspace_id": workspace_id,
                "question": "approved invoices",
                "dataset_ids": ["dataset-1"],
            },
        )
        policy_sim = client.post(
            "/api/v1/ai/policy-assistant",
            headers=headers,
            json={
                "workspace_id": workspace_id,
                "actor": {"actor_type": "human", "roles": ["analyst"], "attributes": {}},
                "resource_attributes": {"dataset_id": "dataset-1"},
                "action": "query",
            },
        )
        eval_generator = client.post(
            "/api/v1/ai/eval-generator",
            headers=headers,
            json={"workspace_id": workspace_id, "questions": ["q1", "q2"]},
        )
        unauthenticated = client.post(
            "/api/v1/ai/ask-sql",
            json={"workspace_id": workspace_id, "question": "what is invoice_count?"},
        )

        def fake_request_json_missing_citations(
            *,
            method: str,
            url: str,
            payload: dict[str, object] | None = None,
            bearer_token: str | None = None,
            gateway_base_url: str | None = None,
            control_plane_base_url: str | None = None,
        ) -> dict[str, object]:
            if url.endswith("/api/v1/gateway/query"):
                query_id = "01HAIEVALQUERY0000000000000"
                build_id = "build_ai_eval_1"
                return {
                    "result": {"rows": [{"invoice_count": 2}]},
                    "provenance": {
                        "provenance_version": "1",
                        "workspace_id": workspace_id,
                        "policy_decision_id": "01HAIEVALPOLICY00000000000",
                        "query_id": query_id,
                        "build_id": build_id,
                        "datasets_used": ["dataset-1"],
                        "citations": [],
                    },
                }
            return fake_request_json(
                method=method,
                url=url,
                payload=payload,
                bearer_token=bearer_token,
                gateway_base_url=gateway_base_url,
                control_plane_base_url=control_plane_base_url,
            )

        ai_service_app.request_json = fake_request_json_missing_citations
        missing_citations = client.post(
            "/api/v1/ai/ask-sql",
            headers=headers,
            json={"workspace_id": workspace_id, "question": "what is invoice_count?"},
        )
        ai_service_app.request_json = fake_request_json
    finally:
        ai_service_app.request_json = original_request_json

    checks = {
        "ask_sql_status": ask_sql.status_code,
        "metric_answer_status": metric_answer.status_code,
        "doc_qa_status": doc_qa.status_code,
        "policy_assistant_status": policy_sim.status_code,
        "eval_generator_status": eval_generator.status_code,
    }
    negative_checks = {
        "ask_sql_unauthenticated_status": unauthenticated.status_code,
        "ask_sql_missing_citations_status": missing_citations.status_code,
        "ask_sql_missing_citations_reason": _extract_error_reason(missing_citations),
    }
    ask_sql_payload = ask_sql.json() if ask_sql.status_code == 200 else {}
    ask_sql_provenance = (
        ask_sql_payload.get("provenance", {})
        if isinstance(ask_sql_payload, dict)
        else {}
    )
    ask_sql_citations = (
        ask_sql_payload.get("citations", [])
        if isinstance(ask_sql_payload, dict)
        else []
    )
    sql_row_count = (
        int(ask_sql_payload.get("answer", {}).get("row_count", 0))
        if isinstance(ask_sql_payload, dict)
        and isinstance(ask_sql_payload.get("answer"), dict)
        else 0
    )
    quality_checks = {
        "sql_correctness": sql_row_count >= 1,
        "provenance_correctness": (
            isinstance(ask_sql_provenance, Mapping)
            and bool(str(ask_sql_provenance.get("query_id", "")).strip())
            and bool(str(ask_sql_provenance.get("build_id", "")).strip())
        ),
        "policy_denial_behavior": negative_checks["ask_sql_unauthenticated_status"] == 403,
        "citation_completeness": (
            negative_checks["ask_sql_missing_citations_status"] == 403
            and negative_checks["ask_sql_missing_citations_reason"] == "ai_citations_required"
            and isinstance(ask_sql_citations, list)
            and len(ask_sql_citations) >= 1
        ),
    }
    base_status = all(code == 200 for code in checks.values()) and all(quality_checks.values())
    report = {
        "status": "pass" if base_status else "fail",
        "smoke": smoke,
        "regression_mode": regression,
        "workspace_id": workspace_id,
        "checks": checks,
        "negative_checks": negative_checks,
        "quality_checks": quality_checks,
        "ask_sql": ask_sql.json() if ask_sql.status_code == 200 else ask_sql.text,
        "metric_answer": metric_answer.json()
        if metric_answer.status_code == 200
        else metric_answer.text,
        "doc_qa": doc_qa.json() if doc_qa.status_code == 200 else doc_qa.text,
        "policy_assistant": policy_sim.json() if policy_sim.status_code == 200 else policy_sim.text,
        "eval_generator": eval_generator.json()
        if eval_generator.status_code == 200
        else eval_generator.text,
    }
    if regression:
        resolved_cases_root = (
            cases_root
            if cases_root is not None
            else Path(__file__).resolve().parents[1] / "tests" / "ai" / "regression_cases"
        )
        cases = load_regression_cases(resolved_cases_root)
        regression_result = evaluate_regression_cases(report=report, cases=cases)
        resolved_baseline_path = (
            baseline_path
            if baseline_path is not None
            else Path(__file__).resolve().parents[1] / "tools" / "ai_eval_baseline.json"
        )
        baseline = _load_baseline(resolved_baseline_path)
        baseline_violations = _evaluate_regression_baseline(
            regression_result=regression_result,
            baseline=baseline,
        )
        regression_payload: dict[str, object] = {
            "cases_root": resolved_cases_root.as_posix(),
            "baseline_path": resolved_baseline_path.as_posix(),
            "summary": regression_result,
            "baseline_violations": baseline_violations,
            "status": (
                "pass"
                if regression_result["status"] == "pass" and not baseline_violations
                else "fail"
            ),
        }
        report["regression"] = regression_payload
        if str(regression_payload.get("status", "fail")) != "pass":
            report["status"] = "fail"
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "results.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Run smoke profile.")
    parser.add_argument("--regression", action="store_true", help="Run regression profile.")
    parser.add_argument(
        "--cases-root",
        default="tests/ai/regression_cases",
        help="Regression-case folder for --regression mode.",
    )
    parser.add_argument(
        "--baseline",
        default="tools/ai_eval_baseline.json",
        help="Regression baseline file for --regression mode.",
    )
    parser.add_argument(
        "--output",
        default="runtime/ai_eval/results.json",
        help="Output report path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    output_path = root / args.output
    report = run_ai_eval_harness(
        output_root=output_path.parent,
        smoke=bool(args.smoke),
        regression=bool(args.regression),
        cases_root=root / str(args.cases_root),
        baseline_path=root / str(args.baseline),
    )
    print(output_path.relative_to(root).as_posix())
    return 0 if report["status"] == "pass" else 1


def _extract_error_reason(response: object) -> str | None:
    json_method = getattr(response, "json", None)
    if not callable(json_method):
        return None
    try:
        payload = json_method()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    details = error.get("details")
    if not isinstance(details, dict):
        return None
    reason = details.get("reason")
    return str(reason) if reason is not None else None


def _load_baseline(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"min_pass_rate": 1.0, "min_passed_cases": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"min_pass_rate": 1.0, "min_passed_cases": 0}
    return payload


def _evaluate_regression_baseline(
    *,
    regression_result: Mapping[str, object],
    baseline: Mapping[str, object],
) -> list[str]:
    violations: list[str] = []
    pass_rate = _to_float(regression_result.get("pass_rate"), default=0.0)
    passed = _to_int(regression_result.get("passed"), default=0)
    min_pass_rate = _to_float(baseline.get("min_pass_rate"), default=1.0)
    min_passed_cases = _to_int(baseline.get("min_passed_cases"), default=0)
    if pass_rate < min_pass_rate:
        violations.append(
            f"pass_rate_below_baseline:{pass_rate:.3f}<{min_pass_rate:.3f}"
        )
    if passed < min_passed_cases:
        violations.append(
            f"passed_cases_below_baseline:{passed}<{min_passed_cases}"
        )
    required_case_ids = baseline.get("required_case_ids", [])
    if isinstance(required_case_ids, list):
        result_rows = regression_result.get("results", [])
        status_by_case: dict[str, str] = {}
        if isinstance(result_rows, list):
            for row in result_rows:
                if not isinstance(row, Mapping):
                    continue
                case_id = str(row.get("case_id", "")).strip()
                status = str(row.get("status", "")).strip()
                if case_id:
                    status_by_case[case_id] = status
        for case_id_raw in required_case_ids:
            case_id = str(case_id_raw).strip()
            if not case_id:
                continue
            if status_by_case.get(case_id) != "pass":
                violations.append(f"required_case_failed:{case_id}")
    return violations


def _to_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return float(stripped)
        except ValueError:
            return default
    return default


def _to_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


if __name__ == "__main__":
    raise SystemExit(main())
