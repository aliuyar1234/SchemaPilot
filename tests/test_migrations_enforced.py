from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.control_plane.app import create_app
from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import Settings
from backend.shared_domain.errors import StartupConfigurationError


def _settings(db_path: Path) -> Settings:
    return Settings(
        profile="team",
        bind_address="0.0.0.0",
        auth_mode="local",
        require_auth_for_non_local=True,
        storage_root="./runtime/storage",
        database_url=f"sqlite:///{db_path.as_posix()}",
    )


def _seed_alembic_revision(db_path: Path, revision: str) -> None:
    connection = sqlite3.connect(db_path.as_posix())
    try:
        connection.execute("create table if not exists alembic_version (version_num varchar(64))")
        connection.execute("delete from alembic_version")
        connection.execute("insert into alembic_version(version_num) values (?)", (revision,))
        connection.commit()
    finally:
        connection.close()


def test_control_plane_non_local_requires_migration_state(tmp_path: Path) -> None:
    db_path = tmp_path / "control_missing_revision.db"
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=lambda: _settings(db_path))


def test_gateway_non_local_requires_migration_state(tmp_path: Path) -> None:
    db_path = tmp_path / "gateway_missing_revision.db"
    with pytest.raises(StartupConfigurationError):
        create_gateway_app(settings_factory=lambda: _settings(db_path))


def test_non_local_allows_expected_revision_present(tmp_path: Path) -> None:
    control_db_path = tmp_path / "control_ok.db"
    gateway_db_path = tmp_path / "gateway_ok.db"
    _seed_alembic_revision(control_db_path, "0003_run_step_dag")
    _seed_alembic_revision(gateway_db_path, "0003_run_step_dag")
    create_app(settings_factory=lambda: _settings(control_db_path))
    create_gateway_app(settings_factory=lambda: _settings(gateway_db_path))


def test_non_local_denies_revision_mismatch(tmp_path: Path) -> None:
    control_db_path = tmp_path / "control_bad_revision.db"
    _seed_alembic_revision(control_db_path, "0000_outdated")
    with pytest.raises(StartupConfigurationError):
        create_app(settings_factory=lambda: _settings(control_db_path))
