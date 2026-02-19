"""Managed Postgres provisioning plan + credential reference helpers."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from backend.shared_domain.secrets_store import SecretsStore


@dataclass(frozen=True)
class ManagedPostgresIdentifiers:
    """Deterministic object identifiers for one workspace target DB."""

    database: str
    schema: str
    reader_role: str
    writer_role: str
    admin_role: str


def _slug(workspace_id: str) -> str:
    token = "".join(ch for ch in workspace_id.lower() if ch.isalnum())
    if token:
        return token[:12]
    digest = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:12]
    return digest


def managed_postgres_identifiers(*, workspace_id: str) -> ManagedPostgresIdentifiers:
    """Generate deterministic database/schema/role names."""
    suffix = _slug(workspace_id)
    prefix = f"sp_{suffix}"
    return ManagedPostgresIdentifiers(
        database=f"{prefix}_db",
        schema=f"{prefix}_schema",
        reader_role=f"{prefix}_reader",
        writer_role=f"{prefix}_writer",
        admin_role=f"{prefix}_admin",
    )


def build_managed_postgres_provision_plan(
    *,
    workspace_id: str,
    target_db_id: str,
    host: str = "postgres",
    port: int = 5432,
) -> dict[str, object]:
    """Build deterministic managed-postgres provisioning plan payload."""
    identifiers = managed_postgres_identifiers(workspace_id=workspace_id)
    statements = [
        f"CREATE ROLE {identifiers.reader_role} LOGIN PASSWORD '<generated>' NOSUPERUSER;",
        f"CREATE ROLE {identifiers.writer_role} LOGIN PASSWORD '<generated>' NOSUPERUSER;",
        f"CREATE ROLE {identifiers.admin_role} LOGIN PASSWORD '<generated>' NOSUPERUSER;",
        f"CREATE DATABASE {identifiers.database};",
        f"\\connect {identifiers.database}",
        f"CREATE SCHEMA IF NOT EXISTS {identifiers.schema};",
        (
            f"GRANT USAGE ON SCHEMA {identifiers.schema} TO {identifiers.reader_role},"
            f" {identifiers.writer_role};"
        ),
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {identifiers.schema} TO {identifiers.reader_role};",
        (
            f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {identifiers.schema}"
            f" TO {identifiers.writer_role};"
        ),
    ]
    return {
        "workspace_id": workspace_id,
        "target_db_id": target_db_id,
        "mode": "managed",
        "db_type": "postgres",
        "connection": {
            "host": host,
            "port": int(port),
            "database": identifiers.database,
            "schema": identifiers.schema,
            "ssl_mode": "disable",
        },
        "identifiers": {
            "database": identifiers.database,
            "schema": identifiers.schema,
            "reader_role": identifiers.reader_role,
            "writer_role": identifiers.writer_role,
            "admin_role": identifiers.admin_role,
        },
        "statements": statements,
    }


def _new_password() -> str:
    return secrets.token_urlsafe(24)


def provision_managed_postgres_secret_refs(
    *,
    secrets_store: SecretsStore,
    workspace_id: str,
    target_db_id: str,
    host: str,
    port: int,
    identifiers: ManagedPostgresIdentifiers,
) -> dict[str, object]:
    """Create credential references (no plaintext return) for reader/writer/admin."""
    scope = f"workspace/{workspace_id}/target-db/{target_db_id}"
    reader_ref = secrets_store.put_secret(
        scope=scope,
        key="reader_credentials",
        value=(
            f"username={identifiers.reader_role};pwd={_new_password()};"
            f"host={host};port={int(port)};database={identifiers.database};schema={identifiers.schema}"
        ),
    )
    writer_ref = secrets_store.put_secret(
        scope=scope,
        key="writer_credentials",
        value=(
            f"username={identifiers.writer_role};pwd={_new_password()};"
            f"host={host};port={int(port)};database={identifiers.database};schema={identifiers.schema}"
        ),
    )
    admin_ref = secrets_store.put_secret(
        scope=scope,
        key="admin_credentials_ephemeral",
        value=(
            f"username={identifiers.admin_role};pwd={_new_password()};"
            f"host={host};port={int(port)};database={identifiers.database};schema={identifiers.schema}"
        ),
    )
    return {
        "reader": reader_ref,
        "writer": writer_ref,
        "admin_ephemeral": admin_ref,
    }
