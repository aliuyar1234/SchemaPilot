"""Add durable audit outbox events table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_audit_outbox_events"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_outbox_events",
        sa.Column("outbox_event_id", sa.String(length=26), primary_key=True),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("audit_event_id", sa.String(length=26), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_audit_outbox_events_service",
        "audit_outbox_events",
        ["service"],
    )
    op.create_index(
        "ix_audit_outbox_events_workspace_id",
        "audit_outbox_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_audit_outbox_events_status",
        "audit_outbox_events",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_outbox_events_status", table_name="audit_outbox_events")
    op.drop_index("ix_audit_outbox_events_workspace_id", table_name="audit_outbox_events")
    op.drop_index("ix_audit_outbox_events_service", table_name="audit_outbox_events")
    op.drop_table("audit_outbox_events")
