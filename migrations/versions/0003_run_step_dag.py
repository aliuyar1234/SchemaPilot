"""Add run step DAG state table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_run_step_dag"
down_revision = "0002_audit_outbox_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs_run_steps",
        sa.Column("run_step_id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("depends_on_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_epoch", sa.Integer(), nullable=True),
        sa.Column("finished_epoch", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("evidence_bundle_uri", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", "step_key", name="uq_runs_run_steps_run_step"),
    )
    op.create_index("ix_runs_run_steps_run_id", "runs_run_steps", ["run_id"])
    op.create_index("ix_runs_run_steps_workspace_id", "runs_run_steps", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_runs_run_steps_workspace_id", table_name="runs_run_steps")
    op.drop_index("ix_runs_run_steps_run_id", table_name="runs_run_steps")
    op.drop_table("runs_run_steps")
