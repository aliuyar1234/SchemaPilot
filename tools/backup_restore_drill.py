#!/usr/bin/env python3
"""Backup/restore drill for local metadata and storage pointers."""

from __future__ import annotations

import importlib
import json
import shutil
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.control_plane.repository import create_target_db_profile, create_workspace
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base, TargetDbState


def _import_tool_module(module_name: str):
    try:
        return importlib.import_module(f"tools.{module_name}")
    except ModuleNotFoundError:
        return importlib.import_module(module_name)


backup_module = _import_tool_module("backup")
restore_module = _import_tool_module("restore")


def _write_seed_state(db_path: Path, storage_path: Path) -> str:
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "gold_latest.json").write_text(
        json.dumps({"snapshot_id": "snap_001"}, sort_keys=True),
        encoding="utf-8",
    )
    Base.metadata.create_all(bind=get_engine(f"sqlite:///{db_path.as_posix()}"))
    target_db_path = storage_path / "target_db" / "serving.sqlite"
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target_db_path.as_posix()) as target_connection:
        target_connection.execute("create table fact_metrics(metric text, value real)")
        target_connection.execute(
            "insert into fact_metrics(metric, value) values ('sum(amount)', 42.0)"
        )
        target_connection.commit()
    session_factory = get_session_factory(f"sqlite:///{db_path.as_posix()}")
    with session_factory() as session:
        workspace = create_workspace(
            session,
            name="Backup Drill Workspace",
            profile="team",
            security_baseline="strict",
        )
        workspace_id = str(workspace["workspace_id"])
        target_profile = create_target_db_profile(
            session,
            workspace_id=workspace_id,
            name="serving-db",
            db_type="sqlite",
            mode="managed",
            connection={"database": target_db_path.as_posix(), "schema": "main"},
        )
        state = session.get(TargetDbState, workspace_id)
        if state is not None:
            state.active_target_db_id = str(target_profile["target_db_id"])
            state.current_build_id = "build_backup"
            state.current_schema_ref = "main"
            state.health_status = "healthy"
        session.commit()
    return workspace_id


def _verify_restored_state(db_path: Path, storage_path: Path, workspace_id: str) -> tuple[int, str]:
    session_factory = get_session_factory(f"sqlite:///{db_path.as_posix()}")
    with session_factory() as session:
        state = session.get(TargetDbState, workspace_id)
    if state is None or not state.active_target_db_id:
        return 0, ""
    latest = json.loads((storage_path / "gold_latest.json").read_text(encoding="utf-8"))
    settings = Settings(
        profile="team",
        bind_address="127.0.0.1",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root=storage_path.as_posix(),
        database_url=f"sqlite:///{db_path.as_posix()}",
        query_engine="target_db",
    )
    gateway = TestClient(create_gateway_app(settings_factory=lambda: settings))
    query_response = gateway.post(
        "/api/v1/gateway/query",
        json={
            "workspace_id": workspace_id,
            "query": {"language": "sql", "text": "select value from fact_metrics"},
            "resource_attributes": {"dataset_id": "dataset-1"},
        },
        headers={"Authorization": "Bearer local-analyst-token"},
    )
    if query_response.status_code != 200:
        return 0, str(latest.get("snapshot_id", ""))
    body = query_response.json()
    value = int(float(body["result"]["rows"][0][0])) if body["result"]["rows"] else 0
    return value, str(latest.get("snapshot_id", ""))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    drill_root = root / "runtime" / "backup_restore_drill"
    source_dir = drill_root / "source"
    backup_dir = drill_root / "backup"
    restored_dir = drill_root / "restored"

    if drill_root.exists():
        shutil.rmtree(drill_root)
    source_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    restored_dir.mkdir(parents=True, exist_ok=True)

    source_db = source_dir / "metadata.db"
    source_storage = source_dir / "storage"
    workspace_id = _write_seed_state(source_db, source_storage)

    backup_module.backup_runtime_state(
        source_db=source_db,
        source_storage=source_storage,
        output_dir=backup_dir,
    )
    restore_module.restore_runtime_state(
        backup_dir=backup_dir,
        restore_dir=restored_dir,
    )

    query_value, snapshot_id = _verify_restored_state(
        restored_dir / "metadata.db",
        restored_dir / "storage",
        workspace_id,
    )
    if query_value != 42 or snapshot_id != "snap_001":
        print("FAIL CHK-BACKUP-RESTORE")
        return 1

    report_path = drill_root / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "workspace_id": workspace_id,
                "gateway_query_value": query_value,
                "snapshot_id": snapshot_id,
                "restored_db": (restored_dir / "metadata.db").relative_to(root).as_posix(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print("PASS CHK-BACKUP-RESTORE")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
