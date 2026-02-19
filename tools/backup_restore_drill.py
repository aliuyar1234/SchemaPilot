#!/usr/bin/env python3
"""Backup/restore drill for local metadata and storage pointers."""

from __future__ import annotations

import hashlib
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _coerce_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _write_seed_state(db_path: Path, storage_path: Path) -> tuple[str, dict[str, str]]:
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "gold_latest.json").write_text(
        json.dumps({"snapshot_id": "snap_001"}, sort_keys=True),
        encoding="utf-8",
    )
    artifact_pointer_path = storage_path / "artifacts" / "registry_state.json"
    artifact_pointer_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_pointer_path.write_text(
        json.dumps(
            {
                "artifact_refs": [
                    {"artifact_id": "artifact_seed_001", "bundle_ref": "evidence://seed_bundle"}
                ],
                "schema_version": "1",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    packs_state_path = storage_path / "packs" / "registry_state.json"
    packs_state_path.parent.mkdir(parents=True, exist_ok=True)
    packs_state_path.write_text(
        json.dumps(
            {
                "active_policy_pack": {"pack_id": "steward-governed", "version": 1},
                "registry_version": "v1",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    Base.metadata.create_all(bind=get_engine(f"sqlite:///{db_path.as_posix()}"))
    target_db_path = storage_path / "target_db" / "serving.sqlite"
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target_db_path.as_posix()) as target_connection:
        target_connection.execute(
            "create table fact_metrics(region text, email text, value real)"
        )
        target_connection.execute(
            "insert into fact_metrics(region, email, value) "
            "values ('eu', 'alice@example.com', 42.0)"
        )
        target_connection.execute(
            "insert into fact_metrics(region, email, value) values ('us', 'bob@example.com', 7.0)"
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
    checksums = {
        "artifact_pointer_checksum": _sha256(artifact_pointer_path),
        "packs_registry_checksum": _sha256(packs_state_path),
    }
    return workspace_id, checksums


def _verify_restored_state(
    db_path: Path,
    storage_path: Path,
    workspace_id: str,
) -> dict[str, object]:
    session_factory = get_session_factory(f"sqlite:///{db_path.as_posix()}")
    with session_factory() as session:
        state = session.get(TargetDbState, workspace_id)
    if state is None or not state.active_target_db_id:
        return {
            "query_value": 0,
            "snapshot_id": "",
            "artifact_pointer_checksum": "",
            "packs_registry_checksum": "",
            "mask_applied": False,
            "provenance_ok": False,
        }
    latest = json.loads((storage_path / "gold_latest.json").read_text(encoding="utf-8"))
    artifact_pointer_path = storage_path / "artifacts" / "registry_state.json"
    packs_state_path = storage_path / "packs" / "registry_state.json"
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
            "query": {
                "language": "sql",
                "text": "select region, email, value from fact_metrics order by region",
            },
            "resource_attributes": {"dataset_id": "dataset-1", "region": "eu"},
        },
        headers={"Authorization": "Bearer local-region-analyst-token"},
    )
    if query_response.status_code != 200:
        return {
            "query_value": 0,
            "snapshot_id": str(latest.get("snapshot_id", "")),
            "artifact_pointer_checksum": "",
            "packs_registry_checksum": "",
            "mask_applied": False,
            "provenance_ok": False,
        }
    body = query_response.json()
    rows = body["result"]["rows"] if isinstance(body.get("result", {}), dict) else []
    row = rows[0] if rows else []
    value = int(float(row[2])) if len(row) > 2 else 0
    masked_email = str(row[1]) if len(row) > 1 else ""
    provenance = body.get("provenance", {})
    provenance_ok = bool(
        isinstance(provenance, dict)
        and str(provenance.get("workspace_id", "")) == workspace_id
        and "policy_decision_id" in provenance
        and "query_id" in provenance
    )
    return {
        "query_value": value,
        "snapshot_id": str(latest.get("snapshot_id", "")),
        "artifact_pointer_checksum": _sha256(artifact_pointer_path)
        if artifact_pointer_path.exists()
        else "",
        "packs_registry_checksum": _sha256(packs_state_path) if packs_state_path.exists() else "",
        "mask_applied": masked_email != "alice@example.com" and bool(masked_email),
        "provenance_ok": provenance_ok,
    }


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
    workspace_id, expected_checksums = _write_seed_state(source_db, source_storage)

    backup_module.backup_runtime_state(
        source_db=source_db,
        source_storage=source_storage,
        output_dir=backup_dir,
    )
    restore_module.restore_runtime_state(
        backup_dir=backup_dir,
        restore_dir=restored_dir,
    )

    verified = _verify_restored_state(
        restored_dir / "metadata.db",
        restored_dir / "storage",
        workspace_id,
    )
    query_value = _coerce_int(verified.get("query_value", 0))
    snapshot_id = str(verified.get("snapshot_id", ""))
    artifact_pointer_checksum = str(verified.get("artifact_pointer_checksum", ""))
    packs_registry_checksum = str(verified.get("packs_registry_checksum", ""))
    mask_applied = bool(verified.get("mask_applied", False))
    provenance_ok = bool(verified.get("provenance_ok", False))
    if (
        query_value != 42
        or snapshot_id != "snap_001"
        or artifact_pointer_checksum != expected_checksums["artifact_pointer_checksum"]
        or packs_registry_checksum != expected_checksums["packs_registry_checksum"]
        or not mask_applied
        or not provenance_ok
    ):
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
                "artifact_pointer_checksum": artifact_pointer_checksum,
                "packs_registry_checksum": packs_registry_checksum,
                "mask_applied": mask_applied,
                "provenance_ok": provenance_ok,
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
