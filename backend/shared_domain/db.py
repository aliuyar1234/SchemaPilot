"""Database primitives for metadata persistence."""

from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.shared_domain.config import Settings
from backend.shared_domain.errors import StartupConfigurationError


class Base(DeclarativeBase):
    """Base declarative class."""


@lru_cache(maxsize=16)
def get_engine(database_url: str) -> Engine:
    """Create and cache SQLAlchemy engine."""
    return create_engine(database_url, future=True)


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create session factory."""
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False, future=True)


def get_db_session(database_url: str) -> Generator[Session, None, None]:
    """Yield a request-scoped session."""
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def prepare_database(settings: Settings) -> None:
    """Prepare metadata database with safe startup behavior."""
    engine = get_engine(settings.database_url)
    if settings.is_local_bind:
        Base.metadata.create_all(bind=engine)
        return
    required_revision = os.getenv("SCHEMAPILOT_REQUIRED_DB_REVISION", "0001_initial_schema")
    ensure_required_revision(engine=engine, required_revision=required_revision)


def ensure_required_revision(*, engine: Engine, required_revision: str) -> None:
    """Require alembic_version table and expected revision in non-local mode."""
    table_names = set(inspect(engine).get_table_names())
    if "alembic_version" not in table_names:
        raise StartupConfigurationError(
            "Database schema migration state is missing.",
            details={"missing_table": "alembic_version"},
        )
    with engine.connect() as connection:
        row = connection.execute(text("select version_num from alembic_version limit 1")).first()
    if row is None:
        raise StartupConfigurationError(
            "Database schema migration state is empty.",
            details={"required_revision": required_revision},
        )
    current_revision = str(row[0])
    if current_revision != required_revision:
        raise StartupConfigurationError(
            "Database schema revision does not match required revision.",
            details={
                "required_revision": required_revision,
                "current_revision": current_revision,
            },
        )
