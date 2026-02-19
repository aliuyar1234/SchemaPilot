from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.control_plane import db_models
from backend.control_plane.app import create_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(tmp_path / "storage").as_posix(),
        database_url=f"sqlite:///{(tmp_path / 'semantic_lifecycle.db').as_posix()}",
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient, *, name: str) -> str:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": name, "profile": "team", "security_baseline": "strict"},
        headers=_headers("local-platform-admin-token"),
    )
    assert response.status_code == 200
    return str(response.json()["workspace_id"])


def _manifest(workspace_id: str, *, with_customer_metric: bool) -> dict[str, object]:
    metrics = [
        {
            "metric_id": "gross_revenue",
            "entity_id": "invoice",
            "aggregation": "sum",
            "field": "amount",
            "expression": "sum(amount)",
        }
    ]
    if with_customer_metric:
        metrics.append(
            {
                "metric_id": "customer_count",
                "entity_id": "customer",
                "aggregation": "count",
                "field": "customer_id",
                "expression": "count(customer_id)",
            }
        )
    return {
        "manifest_version": "1",
        "workspace_id": workspace_id,
        "entities": [
            {
                "entity_id": "invoice",
                "dataset_id": "dataset_invoice",
                "primary_key": "invoice_id",
                "attributes": ["customer_id", "invoice_date"],
            },
            {
                "entity_id": "customer",
                "dataset_id": "dataset_customer",
                "primary_key": "customer_id",
                "attributes": ["customer_name"],
            },
        ],
        "metrics": metrics,
        "joins": [
            {
                "join_id": "invoice_customer",
                "left_entity_id": "invoice",
                "right_entity_id": "customer",
                "left_key": "customer_id",
                "right_key": "customer_id",
                "join_type": "inner",
            }
        ],
    }


def test_semantic_manifest_change_requires_steward_or_admin_role(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client, name="Semantic Role Guard")
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-request",
        json={"semantic_manifest": _manifest(workspace_id, with_customer_metric=False)},
        headers=_headers("local-analyst-token"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "missing_required_role"


def test_semantic_manifest_is_approval_gated_and_rollbackable(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client, name="Semantic Lifecycle")

    first_request = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-request",
        json={"semantic_manifest": _manifest(workspace_id, with_customer_metric=False)},
        headers=_headers("local-data-steward-token"),
    )
    assert first_request.status_code == 200
    first_payload = first_request.json()
    first_change_id = str(first_payload["change_request_id"])
    first_migration_checksum = str(first_payload["migration_plan_checksum"])

    review_tasks = client.get(f"/api/v1/workspaces/{workspace_id}/review_tasks")
    assert review_tasks.status_code == 200
    assert any(
        task["priority"] == "quality_critical"
        and task["blocking"] is True
        and task["proposal_type"] == "semantic_manifest_change_proposal"
        for task in review_tasks.json()
    )

    first_decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-requests/{first_change_id}/decision",
        json={
            "decision": "approve",
            "decision_reason": "publish semantic v1",
            "expected_migration_plan_checksum": first_migration_checksum,
        },
        headers=_headers("local-platform-admin-token"),
    )
    assert first_decision.status_code == 200
    assert first_decision.json()["status"] == "applied"
    effective = client.get(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest",
        headers=_headers("local-platform-admin-token"),
    )
    assert effective.status_code == 200
    first_effective = effective.json()
    assert int(first_effective["version"]) == 1
    assert len(first_effective["manifest"]["metrics"]) == 1

    second_request = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-request",
        json={"semantic_manifest": _manifest(workspace_id, with_customer_metric=True)},
        headers=_headers("local-data-steward-token"),
    )
    assert second_request.status_code == 200
    second_payload = second_request.json()
    second_change_id = str(second_payload["change_request_id"])
    second_migration_checksum = str(second_payload["migration_plan_checksum"])
    second_decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-requests/{second_change_id}/decision",
        json={
            "decision": "approve",
            "decision_reason": "publish semantic v2",
            "expected_migration_plan_checksum": second_migration_checksum,
        },
        headers=_headers("local-platform-admin-token"),
    )
    assert second_decision.status_code == 200
    effective_second = client.get(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest",
        headers=_headers("local-platform-admin-token"),
    )
    assert effective_second.status_code == 200
    second_payload = effective_second.json()
    assert int(second_payload["version"]) == 2
    assert len(second_payload["manifest"]["metrics"]) == 2

    rollback = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/rollback",
        headers=_headers("local-platform-admin-token"),
    )
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "rolled_back"
    rolled_back = rollback.json()["effective_semantic_manifest"]
    assert int(rolled_back["version"]) == 3
    assert len(rolled_back["manifest"]["metrics"]) == 1
    session = get_session_factory(_settings(tmp_path).database_url)()
    try:
        events = (
            session.execute(
                select(db_models.AuditEvent).where(
                    db_models.AuditEvent.workspace_id == workspace_id
                )
            )
            .scalars()
            .all()
        )
        event_types = {event.event_type for event in events}
        assert "semantic_manifest.change_requested" in event_types
        assert "semantic_manifest.change_decided" in event_types
    finally:
        session.close()


def test_semantic_manifest_change_rejects_invalid_manifest(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client, name="Semantic Invalid")
    invalid_manifest = _manifest(workspace_id, with_customer_metric=False)
    invalid_manifest["metrics"] = [  # type: ignore[index]
        {
            "metric_id": "invalid_metric",
            "entity_id": "missing_entity",
            "aggregation": "sum",
            "field": "amount",
            "expression": "sum(amount)",
        }
    ]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-request",
        json={"semantic_manifest": invalid_manifest},
        headers=_headers("local-data-steward-token"),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "POLICY_DENIED"
    assert body["error"]["details"]["reason"] == "invalid_semantic_manifest"


def test_semantic_manifest_apply_requires_migration_checksum(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_factory=lambda: _settings(tmp_path)))
    workspace_id = _create_workspace(client, name="Semantic Checksum Guard")
    request_response = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-request",
        json={"semantic_manifest": _manifest(workspace_id, with_customer_metric=False)},
        headers=_headers("local-data-steward-token"),
    )
    assert request_response.status_code == 200
    change_id = str(request_response.json()["change_request_id"])
    decision = client.post(
        f"/api/v1/workspaces/{workspace_id}/semantic-manifest/change-requests/{change_id}/decision",
        json={"decision": "approve", "decision_reason": "missing expected checksum"},
        headers=_headers("local-platform-admin-token"),
    )
    assert decision.status_code == 403
    assert decision.json()["error"]["details"]["reason"] == "migration_plan_checksum_required"
