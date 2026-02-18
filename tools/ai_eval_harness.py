#!/usr/bin/env python3
"""Deterministic AI eval harness for SQL agent and retrieval flows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import backend.ai_service.app as ai_service_app
from backend.ai_service.app import create_ai_service_app
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


def run_ai_eval_harness(*, output_root: Path, smoke: bool) -> dict[str, object]:
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
    ) -> dict[str, object]:
        _ = (method, payload, bearer_token)
        if url.endswith("/api/v1/gateway/query"):
            return {
                "result": {"rows": [{"invoice_count": 2}]},
                "provenance": {"provenance_version": "1", "citations": []},
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
            json={"workspace_id": workspace_id, "question": "approved invoices"},
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
    finally:
        ai_service_app.request_json = original_request_json

    checks = {
        "ask_sql_status": ask_sql.status_code,
        "metric_answer_status": metric_answer.status_code,
        "doc_qa_status": doc_qa.status_code,
        "policy_assistant_status": policy_sim.status_code,
        "eval_generator_status": eval_generator.status_code,
    }
    report = {
        "status": "pass" if all(code == 200 for code in checks.values()) else "fail",
        "smoke": smoke,
        "workspace_id": workspace_id,
        "checks": checks,
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
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "results.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Run smoke profile.")
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
    report = run_ai_eval_harness(output_root=output_path.parent, smoke=bool(args.smoke))
    print(output_path.relative_to(root).as_posix())
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
