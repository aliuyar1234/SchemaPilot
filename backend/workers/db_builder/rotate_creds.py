"""Target DB credential rotation helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass

from backend.shared_domain.metadata_models import TargetDbProfile
from backend.shared_domain.secrets_store import SecretsStore
from backend.workers.db_builder.provision_postgres import (
    managed_postgres_identifiers,
    provision_managed_postgres_secret_refs,
)


@dataclass(frozen=True)
class TargetDbCredentialRotationResult:
    """Result of one target-db credential rotation execution."""

    previous_refs: dict[str, str]
    rotated_refs: dict[str, str]
    revoked_refs: list[str]
    dual_validity_window_seconds: int


def rotate_target_db_credentials(
    *,
    workspace_id: str,
    target_db_id: str,
    profile: TargetDbProfile,
    secrets_store: SecretsStore,
    dual_validity_window_seconds: int = 300,
    rotation_epoch: int | None = None,
) -> TargetDbCredentialRotationResult:
    """Rotate target-db credential references deterministically."""

    previous_refs = _normalized_refs(profile.credential_refs_json)
    if profile.db_type == "postgres" and profile.mode == "managed":
        host = str(profile.connection_json.get("host", "postgres"))
        port_raw = profile.connection_json.get("port")
        port = _as_int(port_raw, default=5432)
        identifiers = managed_postgres_identifiers(workspace_id=workspace_id)
        rotated_raw = provision_managed_postgres_secret_refs(
            secrets_store=secrets_store,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            host=host,
            port=port,
            identifiers=identifiers,
        )
        rotated_refs = _normalized_refs(rotated_raw)
    else:
        stamp = rotation_epoch if rotation_epoch is not None else int(time.time())
        rotated_refs = _rotate_generic_refs(
            previous_refs=previous_refs,
            workspace_id=workspace_id,
            target_db_id=target_db_id,
            stamp=stamp,
        )

    revoked_refs = sorted(
        {
            reference
            for reference in previous_refs.values()
            if reference and reference not in set(rotated_refs.values())
        }
    )
    return TargetDbCredentialRotationResult(
        previous_refs=previous_refs,
        rotated_refs=rotated_refs,
        revoked_refs=revoked_refs,
        dual_validity_window_seconds=max(int(dual_validity_window_seconds), 0),
    )


def _normalized_refs(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    refs: dict[str, str] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if not key_text or not value_text:
            continue
        refs[key_text] = value_text
    return refs


def _rotate_generic_refs(
    *,
    previous_refs: dict[str, str],
    workspace_id: str,
    target_db_id: str,
    stamp: int,
) -> dict[str, str]:
    if previous_refs:
        return {
            role: f"{_strip_rotation_suffix(reference)}#rotated-{stamp}"
            for role, reference in sorted(previous_refs.items())
        }
    return {
        "reader": (
            f"secret://workspace/{workspace_id}/target_db/{target_db_id}"
            f"/reader#rotated-{stamp}"
        ),
        "writer": (
            f"secret://workspace/{workspace_id}/target_db/{target_db_id}"
            f"/writer#rotated-{stamp}"
        ),
    }


def _strip_rotation_suffix(reference: str) -> str:
    marker = "#rotated-"
    if marker not in reference:
        return reference
    return reference.split(marker, 1)[0]


def _as_int(value: object, *, default: int) -> int:
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
