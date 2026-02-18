from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from backend.ai_service.sql_agent import generate_sql_agent_plan, validate_sql_agent_plan
from backend.control_plane.repository import create_workspace
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import Base, GovernancePolicy


def _seed_semantic_manifest(session: Session) -> str:
    workspace = create_workspace(
        session,
        name="SQL Agent Workspace",
        profile="starter",
        security_baseline="standard",
    )
    workspace_id = str(workspace["workspace_id"])
    manifest = {
        "workspace_id": workspace_id,
        "manifest_version": "1.0.0",
        "entities": [{"entity_id": "invoice", "dataset_id": "dataset-1"}],
        "dimensions": [{"dimension_id": "region", "entity_id": "invoice"}],
        "metrics": [
            {"metric_id": "invoice_count", "entity_id": "invoice", "expression": "count(*)"},
            {
                "metric_id": "invoice_amount_sum",
                "entity_id": "invoice",
                "expression": "sum(amount)",
            },
        ],
        "joins": [],
    }
    session.add(
        GovernancePolicy(
            policy_id=new_ulid(),
            workspace_id=workspace_id,
            policy_type="semantic_manifest",
            definition_ref=json.dumps({"semantic_manifest": manifest}, sort_keys=True),
            status="active",
        )
    )
    session.flush()
    return workspace_id


def test_generate_sql_agent_plan_prefers_explicit_metric(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'sql_agent.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        workspace_id = _seed_semantic_manifest(session)
        session.commit()

    plan = generate_sql_agent_plan(
        workspace_id=workspace_id,
        question="show me revenue by region",
        session_factory=session_factory,
        metric_id="invoice_amount_sum",
        group_by=["region"],
    )
    assert plan.semantic_query["metric_id"] == "invoice_amount_sum"
    assert plan.semantic_query["group_by"] == ["region"]
    assert plan.confidence >= 0.8


def test_validate_sql_agent_plan_rejects_invalid_identifiers() -> None:
    from backend.ai_service.sql_agent import SqlAgentPlan

    plan = SqlAgentPlan(
        workspace_id="w1",
        semantic_query={"metric_id": "bad-metric", "group_by": ["region"]},
        confidence=0.1,
        warnings=[],
    )
    try:
        validate_sql_agent_plan(plan)
    except ValueError as exc:
        assert str(exc) == "semantic_metric_invalid"
    else:  # pragma: no cover
        raise AssertionError("expected semantic_metric_invalid")
