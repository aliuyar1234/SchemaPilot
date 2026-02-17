"""Database primitives for metadata persistence."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


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
