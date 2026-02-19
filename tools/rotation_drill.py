#!/usr/bin/env python3
"""Run secrets/JWKS rotation drill with deterministic evidence output."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from backend.shared_domain.auth import clear_jwks_cache, load_jwks_keys_for_settings
from backend.shared_domain.config import Settings
from backend.shared_domain.metadata_models import TargetDbProfile
from backend.shared_domain.secrets_store import load_secrets_store
from backend.workers.db_builder.rotate_creds import rotate_target_db_credentials

ROTATION_STAMP = 1_700_000_000


def _b64url_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _write_oct_jwks(path: Path, *, secret: bytes, kid: str) -> str:
    payload = {
        "keys": [
            {
                "kty": "oct",
                "kid": kid,
                "alg": "HS256",
                "k": _b64url_bytes(secret),
                "use": "sig",
            }
        ]
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path.as_uri()


def _build_settings(*, drill_root: Path, jwks_url: str) -> Settings:
    return Settings(
        profile="enterprise",
        bind_address="127.0.0.1",
        auth_mode="oidc_jwt",
        require_auth_for_non_local=True,
        storage_root=(drill_root / "storage").as_posix(),
        database_url=f"sqlite:///{(drill_root / 'rotation_drill.db').as_posix()}",
        secrets_store_backend="local_encrypted",
        secrets_store_root=(drill_root / "secrets").as_posix(),
        secrets_master_key="rotation-drill-master-key",
        oidc_jwks_url=jwks_url,
        oidc_required_issuer="https://rotation.example",
    )


def _build_profile(*, workspace_id: str, target_db_id: str) -> TargetDbProfile:
    return TargetDbProfile(
        target_db_id=target_db_id,
        workspace_id=workspace_id,
        name="rotation-drill-target",
        db_type="postgres",
        mode="managed",
        status="active",
        desired_config_hash="rotation-drill",
        connection_json={"host": "postgres", "port": 5432, "database": "drill"},
        credential_refs_json={
            "reader": "secret://legacy/workspace/w1/target_db/t1/reader",
            "writer": "secret://legacy/workspace/w1/target_db/t1/writer",
        },
        disabled=False,
    )


def _connection_fingerprint(connection: dict[str, object]) -> str:
    canonical = json.dumps(connection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    drill_root = root / "runtime" / "rotation_drill"
    drill_root.mkdir(parents=True, exist_ok=True)
    jwks_path = drill_root / "jwks.json"
    jwks_url = _write_oct_jwks(jwks_path, secret=b"rotation-key-a", kid="kid-a")
    settings = _build_settings(drill_root=drill_root, jwks_url=jwks_url)
    secrets_store = load_secrets_store(settings)

    workspace_id = "rotation-workspace"
    target_db_id = "rotation-target"
    profile = _build_profile(workspace_id=workspace_id, target_db_id=target_db_id)
    previous_refs = {str(k): str(v) for k, v in profile.credential_refs_json.items()}
    rotation = rotate_target_db_credentials(
        workspace_id=workspace_id,
        target_db_id=target_db_id,
        profile=profile,
        secrets_store=secrets_store,
        dual_validity_window_seconds=300,
        rotation_epoch=ROTATION_STAMP,
    )

    reader_rotated = rotation.rotated_refs.get("reader", "") != previous_refs.get("reader", "")
    writer_rotated = rotation.rotated_refs.get("writer", "") != previous_refs.get("writer", "")
    if not (reader_rotated and writer_rotated):
        print("FAIL target-db credential rotation did not rotate reader/writer refs")
        return 1
    if not rotation.revoked_refs:
        print("FAIL target-db credential rotation did not produce revoked refs")
        return 1

    clear_jwks_cache(jwks_url=jwks_url)
    keys_before = load_jwks_keys_for_settings(settings=settings)
    _write_oct_jwks(jwks_path, secret=b"rotation-key-b", kid="kid-b")
    keys_cached = load_jwks_keys_for_settings(settings=settings)
    clear_jwks_cache(jwks_url=jwks_url)
    keys_after = load_jwks_keys_for_settings(settings=settings)
    if not keys_before or not keys_after:
        print("FAIL jwks rotation drill could not load keys")
        return 1
    cached_stale = str(keys_cached[0].get("kid", "")) == str(keys_before[0].get("kid", ""))
    cache_invalidated = str(keys_after[0].get("kid", "")) == "kid-b"
    if not (cached_stale and cache_invalidated):
        print("FAIL jwks rotation cache invalidation check failed")
        return 1

    report_path = drill_root / "report.json"
    report_payload = {
        "status": "pass",
        "workspace_id": workspace_id,
        "target_db_id": target_db_id,
        "gateway_reader_rotated": reader_rotated,
        "worker_writer_rotated": writer_rotated,
        "revoked_credential_refs": rotation.revoked_refs,
        "dual_validity_window_seconds": rotation.dual_validity_window_seconds,
        "rotated_credential_ref_count": len(rotation.rotated_refs),
        "jwks_cache_invalidated": cache_invalidated,
        "connection_fingerprint": _connection_fingerprint(dict(profile.connection_json)),
    }
    report_path.write_text(
        json.dumps(report_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print("PASS rotation drill")
    print("PASS secrets rotation drill")
    print(report_path.relative_to(root).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
