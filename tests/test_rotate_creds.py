from __future__ import annotations

from pathlib import Path

from backend.shared_domain.metadata_models import TargetDbProfile
from backend.shared_domain.secrets_store import LocalEncryptedSecretsStore
from backend.workers.db_builder.rotate_creds import rotate_target_db_credentials


def _profile(
    *,
    workspace_id: str,
    target_db_id: str,
    db_type: str,
    mode: str,
    credential_refs: dict[str, str],
) -> TargetDbProfile:
    return TargetDbProfile(
        target_db_id=target_db_id,
        workspace_id=workspace_id,
        name="target-db",
        db_type=db_type,
        mode=mode,
        status="active",
        desired_config_hash="hash",
        connection_json={"host": "postgres", "port": 5432, "database": "db"},
        credential_refs_json=credential_refs,
        disabled=False,
    )


def test_rotate_creds_generic_external_rotates_and_revokes(tmp_path: Path) -> None:
    store = LocalEncryptedSecretsStore(root=tmp_path / "secrets", master_key="test-master")
    profile = _profile(
        workspace_id="w1",
        target_db_id="t1",
        db_type="sqlite",
        mode="external",
        credential_refs={"reader": "secret://legacy/reader", "writer": "secret://legacy/writer"},
    )
    result = rotate_target_db_credentials(
        workspace_id="w1",
        target_db_id="t1",
        profile=profile,
        secrets_store=store,
        rotation_epoch=123,
        dual_validity_window_seconds=120,
    )
    assert result.rotated_refs["reader"].endswith("#rotated-123")
    assert result.rotated_refs["writer"].endswith("#rotated-123")
    assert sorted(result.revoked_refs) == ["secret://legacy/reader", "secret://legacy/writer"]
    assert result.dual_validity_window_seconds == 120


def test_rotate_creds_managed_postgres_generates_secret_refs(tmp_path: Path) -> None:
    store = LocalEncryptedSecretsStore(root=tmp_path / "secrets", master_key="test-master")
    profile = _profile(
        workspace_id="w1",
        target_db_id="t1",
        db_type="postgres",
        mode="managed",
        credential_refs={"reader": "secret://legacy/reader", "writer": "secret://legacy/writer"},
    )
    result = rotate_target_db_credentials(
        workspace_id="w1",
        target_db_id="t1",
        profile=profile,
        secrets_store=store,
    )
    assert "reader" in result.rotated_refs
    assert "writer" in result.rotated_refs
    assert result.revoked_refs
