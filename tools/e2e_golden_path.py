#!/usr/bin/env python3
"""Deterministic local golden-path harness: folder -> discover -> gold -> gateway query."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from backend.control_plane.app import create_app as create_control_plane_app
from backend.control_plane.repository import (
    create_run,
    create_source,
    create_target_db_profile,
    create_workspace,
    get_run,
)
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.contract_reports import write_build_contract_report
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base, TargetDbState
from backend.workers.gold import build_gold_snapshot
from backend.workers.run_processor import process_run_by_id


def run_golden_path(*, root: Path, smoke: bool) -> dict[str, object]:
    """Execute deterministic golden path and return machine-readable report."""
    runtime_root = root / "runtime" / "e2e_golden_path"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    storage_root = runtime_root / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)
    exports_root = runtime_root / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    (exports_root / "invoices.csv").write_text(
        "invoice_id,amount,region\n1001,1200.5,eu\n1002,900.0,us\n",
        encoding="utf-8",
    )
    database_path = runtime_root / "e2e.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    started = perf_counter()
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Golden Path Workspace",
            profile="starter",
            security_baseline="standard",
        )
        workspace_id = str(workspace["workspace_id"])
        create_source(
            session,
            workspace_id=workspace_id,
            source_type="filesystem",
            scope={"root_path": exports_root.as_posix(), "include_globs": ["**/*.csv"]},
            display_name="Golden Path Source",
        )
        run = create_run(session, workspace_id=workspace_id, run_type="discover")
        run_id = str(run["run_id"])
        session.commit()

    with session_factory() as session:
        run_result = process_run_by_id(
            session,
            run_id=run_id,
            storage_root=storage_root.as_posix(),
            strict_ingest=True,
        )
        session.commit()
    if run_result is None or run_result.status != "succeeded":
        return {
            "status": "fail",
            "reason": "discover_run_failed",
            "run_result": None if run_result is None else run_result.output_refs,
        }

    gold = build_gold_snapshot(
        workspace_id=workspace_id,
        model_name="orders",
        silver_rows=[
            {"amount": 1200.5},
            {"amount": 900.0},
        ],
        metric_field="amount",
        output_root=storage_root.as_posix(),
        snapshot_id="gold_snap_001",
        allow_publish=True,
    )
    gold_rollback = build_gold_snapshot(
        workspace_id=workspace_id,
        model_name="orders",
        silver_rows=[{"amount": 1100.0}],
        metric_field="amount",
        output_root=storage_root.as_posix(),
        snapshot_id="gold_snap_rollback",
        allow_publish=True,
    )

    target_db_file = runtime_root / "target_db" / "serving.sqlite"
    target_db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target_db_file.as_posix()) as target_conn:
        target_conn.execute("create table fact_metrics (metric text, value real)")
        target_conn.execute(
            "insert into fact_metrics(metric, value) values ('sum(amount)', 2100.5)"
        )
        target_conn.commit()

    with session_factory() as session:
        target_profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="sqlite",
            mode="managed",
            connection={"database": target_db_file.as_posix(), "schema": "main"},
        )
        state_row = session.get(TargetDbState, workspace_id)
        if state_row is None:
            return {"status": "fail", "reason": "target_db_state_missing_after_profile_create"}
        state_row.active_target_db_id = str(target_profile["target_db_id"])
        state_row.current_build_id = "build_old"
        state_row.current_schema_ref = "main"
        state_row.health_status = "healthy"
        session.commit()

    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build_old",
        contracts_passed=True,
        failures=[],
        storage_root=storage_root.as_posix(),
    )
    write_build_contract_report(
        workspace_id=workspace_id,
        build_id="build_new",
        contracts_passed=True,
        failures=[],
        storage_root=storage_root.as_posix(),
    )

    cp_settings = Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=storage_root.as_posix(),
        database_url=database_url,
    )
    control_plane = TestClient(create_control_plane_app(settings_factory=lambda: cp_settings))
    publish_old = control_plane.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build_old/publish",
        json={
            "snapshot_id": gold.snapshot_id,
            "model_name": "orders",
            "target_db_id": target_profile["target_db_id"],
            "target_schema_ref": "main",
        },
        headers={"Authorization": "Bearer local-data-steward-token"},
    )
    if publish_old.status_code != 200:
        return {
            "status": "fail",
            "reason": "publish_old_failed",
            "control_plane_status": publish_old.status_code,
            "control_plane_body": publish_old.json(),
        }
    publish_new = control_plane.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build_new/publish",
        json={
            "snapshot_id": gold_rollback.snapshot_id,
            "model_name": "orders",
            "target_db_id": target_profile["target_db_id"],
            "target_schema_ref": "main",
        },
        headers={"Authorization": "Bearer local-data-steward-token"},
    )
    if publish_new.status_code != 200:
        return {
            "status": "fail",
            "reason": "publish_new_failed",
            "control_plane_status": publish_new.status_code,
            "control_plane_body": publish_new.json(),
        }
    rollback = control_plane.post(
        f"/api/v1/workspaces/{workspace_id}/builds/build_old/rollback",
        json={},
        headers={"Authorization": "Bearer local-platform-admin-token"},
    )
    if rollback.status_code != 200:
        return {
            "status": "fail",
            "reason": "rollback_failed",
            "control_plane_status": rollback.status_code,
            "control_plane_body": rollback.json(),
        }
    rollback_body = rollback.json()
    rolled_state = rollback_body.get("target_db_state_after", {})
    rollback_build_id = (
        str(rolled_state.get("current_build_id", ""))
        if isinstance(rolled_state, dict)
        else ""
    )
    if rollback_build_id != "build_old":
        return {
            "status": "fail",
            "reason": "rollback_state_mismatch",
            "rollback_body": rollback_body,
        }

    settings = Settings(
        profile="starter",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=storage_root.as_posix(),
        database_url=database_url,
        query_engine="target_db",
    )
    gateway = TestClient(create_gateway_app(settings_factory=lambda: settings))
    query_response = gateway.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select metric, value from fact_metrics"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers={"Authorization": "Bearer local-analyst-token"},
    )
    if query_response.status_code != 200:
        return {
            "status": "fail",
            "reason": "gateway_query_failed",
            "gateway_status": query_response.status_code,
            "gateway_body": query_response.json(),
        }
    body = query_response.json()
    if int(body["result"]["row_count"]) != 1:
        return {
            "status": "fail",
            "reason": "unexpected_query_row_count",
            "actual_row_count": body["result"]["row_count"],
        }
    if body["provenance"]["provenance_version"] != "1":
        return {
            "status": "fail",
            "reason": "unexpected_provenance_version",
            "actual": body["provenance"]["provenance_version"],
        }
    run_state: dict[str, object] | None
    with session_factory() as session:
        run_state = get_run(session, workspace_id=workspace_id, run_id=run_id)
    report = {
        "status": "pass",
        "duration_ms": round((perf_counter() - started) * 1000.0, 3),
        "workspace_id": workspace_id,
        "run_id": run_id,
        "run_status": run_state["status"] if isinstance(run_state, dict) else "unknown",
        "gold_snapshot_id": gold.snapshot_id,
        "gateway_metric": body["result"]["rows"][0][0],
        "gateway_value": body["result"]["rows"][0][1],
        "provenance_version": body["provenance"]["provenance_version"],
        "provenance_target_db_id": body["provenance"].get("target_db_id"),
        "provenance_target_schema_ref": body["provenance"].get("target_schema_ref"),
        "rollback_build_id": rollback_build_id,
        "smoke": smoke,
    }
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Run minimal deterministic scenario.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    report = run_golden_path(root=root, smoke=args.smoke)
    report_path = root / "runtime" / "e2e_golden_path" / "results.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if report.get("status") != "pass":
        print("FAIL e2e golden path")
        print(report_path.relative_to(root).as_posix())
        return 1
    print("PASS e2e golden path")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
