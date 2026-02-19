from __future__ import annotations

import json
from pathlib import Path

from backend.shared_domain.audit_models import AccessDecision, AuditEvent
from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.ids import new_ulid
from backend.shared_domain.metadata_models import Base, GovernancePolicy, RunRecord, Workspace
from tools.auditor_export import export_auditor_bundle


def test_auditor_export_is_redaction_safe_and_signed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'auditor.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        workspace_id = "w1"
        session.add(
            Workspace(
                workspace_id=workspace_id,
                name="Auditor Workspace",
                profile="enterprise",
                security_baseline="strict",
            )
        )
        session.add(
            GovernancePolicy(
                policy_id=new_ulid(),
                workspace_id=workspace_id,
                policy_type="policy_pack",
                definition_ref=json.dumps({"pack": "enterprise", "token": "sensitive-raw-value"}),
                status="active",
            )
        )
        audit_event_id = new_ulid()
        session.add(
            AuditEvent(
                audit_event_id=audit_event_id,
                workspace_id=workspace_id,
                actor_id="user:admin",
                event_type="promotion.attestation_recorded",
                event_json={"attestation": "ok"},
                correlation_id=new_ulid(),
            )
        )
        session.add(
            AccessDecision(
                decision_id=new_ulid(),
                workspace_id=workspace_id,
                actor_id="user:admin",
                request_context_json={"endpoint": "query"},
                resources_json={"endpoint": "query"},
                result="allow",
                applied_filters_json={},
                applied_masks_json={},
                audit_event_id=audit_event_id,
            )
        )
        session.add(
            RunRecord(
                run_id=new_ulid(),
                workspace_id=workspace_id,
                run_type="discover",
                status="succeeded",
                input_refs_json={"source_ids": ["s1"]},
                output_refs_json={"dataset_ids": ["dataset-1"]},
            )
        )
        session.commit()

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"policies": [{"id": "starter"}], "semantic": [{"id": "core"}]}),
        encoding="utf-8",
    )
    output_path = tmp_path / "auditor_export.json"
    result = export_auditor_bundle(
        database_url=database_url,
        output_path=output_path,
        packs_registry_path=registry_path,
        signing_key="auditor-signing-key",
    )
    assert result["status"] == "pass"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["signature"]["algorithm"] == "hmac-sha256"
    bundle = payload["bundle"]
    assert bundle["policy_decisions"]
    first_policy = bundle["policy_decisions"][0]
    assert "definition_checksum" in first_policy
    assert "definition_ref" not in first_policy
    serialized = json.dumps(bundle, sort_keys=True)
    assert "sensitive-raw-value" not in serialized


def test_auditor_export_is_deterministic(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'auditor_det.db').as_posix()}"
    Base.metadata.create_all(bind=get_engine(database_url))
    output_a = tmp_path / "a.json"
    output_b = tmp_path / "b.json"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"policies": []}), encoding="utf-8")
    first = export_auditor_bundle(
        database_url=database_url,
        output_path=output_a,
        packs_registry_path=registry_path,
        signing_key="auditor-signing-key",
    )
    second = export_auditor_bundle(
        database_url=database_url,
        output_path=output_b,
        packs_registry_path=registry_path,
        signing_key="auditor-signing-key",
    )
    assert first["bundle_checksum"] == second["bundle_checksum"]
    payload_a = json.loads(output_a.read_text(encoding="utf-8"))
    payload_b = json.loads(output_b.read_text(encoding="utf-8"))
    assert payload_a["bundle"] == payload_b["bundle"]
