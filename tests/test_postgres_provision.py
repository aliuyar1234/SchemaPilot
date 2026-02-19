from __future__ import annotations

from pathlib import Path

from backend.shared_domain.secrets_store import LocalEncryptedSecretsStore
from backend.workers.db_builder.provision_postgres import (
    build_managed_postgres_provision_plan,
    managed_postgres_identifiers,
    provision_managed_postgres_secret_refs,
)


def test_managed_postgres_plan_is_deterministic() -> None:
    first = build_managed_postgres_provision_plan(
        workspace_id="ws_1234-abcd",
        target_db_id="tdb_1",
    )
    second = build_managed_postgres_provision_plan(
        workspace_id="ws_1234-abcd",
        target_db_id="tdb_1",
    )
    assert first == second
    assert first["connection"]["host"] == "postgres"
    assert first["connection"]["port"] == 5432
    assert first["identifiers"]["reader_role"].endswith("_reader")


def test_managed_postgres_secret_refs_do_not_return_plaintext(tmp_path: Path) -> None:
    store = LocalEncryptedSecretsStore(root=tmp_path / "secrets", master_key="test-key")
    identifiers = managed_postgres_identifiers(workspace_id="ws_prod")
    refs = provision_managed_postgres_secret_refs(
        secrets_store=store,
        workspace_id="ws_prod",
        target_db_id="tdb_1",
        host="postgres",
        port=5432,
        identifiers=identifiers,
    )
    assert refs["reader"].startswith("secret://local/")
    assert refs["writer"].startswith("secret://local/")
    assert refs["admin_ephemeral"].startswith("secret://local/")
    reader_secret = store.get_secret(str(refs["reader"]))
    assert identifiers.reader_role in reader_secret
    assert "pwd=" in reader_secret
