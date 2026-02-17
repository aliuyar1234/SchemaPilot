"""Shared SQLAlchemy models for append-only audit surfaces."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared_domain.db import Base


class AuditEvent(Base):
    """Normative audit.audit_events append-only table."""

    __tablename__ = "audit_audit_events"

    audit_event_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_json: Mapped[dict[str, object]] = mapped_column(SQLiteJSON, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(26), nullable=False)


class AccessDecision(Base):
    """Normative audit.access_decisions append-only table."""

    __tablename__ = "audit_access_decisions"

    decision_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_context_json: Mapped[dict[str, object]] = mapped_column(SQLiteJSON, nullable=False)
    resources_json: Mapped[dict[str, object]] = mapped_column(SQLiteJSON, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    applied_filters_json: Mapped[dict[str, object]] = mapped_column(SQLiteJSON, nullable=False)
    applied_masks_json: Mapped[dict[str, object]] = mapped_column(SQLiteJSON, nullable=False)
    audit_event_id: Mapped[str] = mapped_column(String(26), nullable=False)
