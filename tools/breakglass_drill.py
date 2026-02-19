#!/usr/bin/env python3
"""Run break-glass end-to-end drill (grant -> query tag -> auto revoke)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_session_factory
from backend.shared_domain.metadata_models import AuditEvent, GovernancePolicy


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(*, drill_root: Path) -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=(drill_root / "storage").as_posix(),
        database_url=f"sqlite:///{(drill_root / 'breakglass_drill.db').as_posix()}",
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    drill_root = root / "runtime" / "breakglass_drill"
    drill_root.mkdir(parents=True, exist_ok=True)
    settings = _settings(drill_root=drill_root)

    control_plane = TestClient(create_app(settings_factory=lambda: settings))
    gateway = TestClient(create_gateway_app(settings_factory=lambda: settings))

    workspace_resp = control_plane.post(
        "/api/v1/workspaces",
        json={
            "name": "Breakglass Drill",
            "profile": "enterprise",
            "security_baseline": "strict",
        },
        headers=_headers("local-platform-admin-token"),
    )
    if workspace_resp.status_code != 200:
        print("FAIL workspace creation failed")
        return 1
    workspace_id = str(workspace_resp.json()["workspace_id"])

    created = control_plane.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests",
        json={"actor_id": "user:local_analyst", "ttl_seconds": 1},
        headers=_headers("local-data-steward-token"),
    )
    if created.status_code != 200:
        print(f"FAIL breakglass request creation failed: {created.text}")
        return 1
    request_id = str(created.json()["request_id"])

    first = control_plane.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve",
        json={"decision": "approve"},
        headers=_headers("local-data-steward-token"),
    )
    if first.status_code != 200:
        print(f"FAIL first breakglass approval failed: {first.text}")
        return 1
    second = control_plane.post(
        f"/api/v1/workspaces/{workspace_id}/breakglass/requests/{request_id}/approve",
        json={"decision": "approve"},
        headers=_headers("local-platform-admin-token"),
    )
    if second.status_code != 200:
        print(f"FAIL second breakglass approval failed: {second.text}")
        return 1

    first_query = gateway.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_headers("local-analyst-token"),
    )
    if first_query.status_code != 200:
        print(f"FAIL breakglass tagged query failed: {first_query.text}")
        return 1
    provenance = first_query.json().get("provenance", {})
    breakglass_tagged = bool(provenance.get("breakglass", False))
    tagged_request_id = str(provenance.get("breakglass_request_id", "")).strip()
    if not breakglass_tagged or tagged_request_id != request_id:
        print("FAIL breakglass provenance tagging missing")
        return 1

    time.sleep(2.1)
    second_query = gateway.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select 1 as one"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers=_headers("local-analyst-token"),
    )
    if second_query.status_code != 200:
        print(f"FAIL post-expiry query failed: {second_query.text}")
        return 1
    second_provenance = second_query.json().get("provenance", {})
    auto_revoked = not bool(second_provenance.get("breakglass", False))

    session = get_session_factory(settings.database_url)()
    try:
        request_row = session.get(GovernancePolicy, request_id)
        grant_id = str(second.json().get("grant_policy_id", "")).strip()
        grant_row = session.get(GovernancePolicy, grant_id) if grant_id else None
        auto_revoke_event = (
            session.execute(
                select(AuditEvent).where(
                    AuditEvent.workspace_id == workspace_id,
                    AuditEvent.event_type == "breakglass.auto_revoked",
                )
            )
            .scalars()
            .first()
        )
        request_status = str(request_row.status) if request_row is not None else ""
        grant_status = str(grant_row.status) if grant_row is not None else ""
    finally:
        session.close()

    if not auto_revoked:
        print("FAIL breakglass auto revoke did not clear provenance tag")
        return 1
    if request_status != "expired":
        print("FAIL breakglass request not marked expired")
        return 1
    if grant_status != "expired":
        print("FAIL breakglass grant not marked expired")
        return 1
    if auto_revoke_event is None:
        print("FAIL breakglass auto revoke event missing")
        return 1

    report_path = drill_root / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "workspace_id": workspace_id,
                "request_id": request_id,
                "grant_policy_id": grant_id,
                "breakglass_tagged_query": breakglass_tagged,
                "auto_revoked": auto_revoked,
                "request_status": request_status,
                "grant_status": grant_status,
                "auto_revoke_event_id": auto_revoke_event.audit_event_id,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print("PASS breakglass drill")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
