"""Initial metadata schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("profile", sa.String(length=32), nullable=False),
        sa.Column("security_baseline", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "catalog_sources",
        sa.Column("source_id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("credentials_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"]),
    )
    op.create_index("ix_catalog_sources_workspace_id", "catalog_sources", ["workspace_id"])

    op.create_table(
        "catalog_datasets",
        sa.Column("dataset_id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("logical_name", sa.Text(), nullable=False),
        sa.Column("physical_locator", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("sensitivity_summary_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_catalog_datasets_workspace_id", "catalog_datasets", ["workspace_id"])

    op.create_table(
        "runs_runs",
        sa.Column("run_id", sa.String(length=26), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_refs_json", sa.JSON(), nullable=False),
        sa.Column("output_refs_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_runs_runs_workspace_id", "runs_runs", ["workspace_id"])

    op.create_table(
        "review_proposals",
        sa.Column("proposal_id", sa.String(length=26), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_bundle_uri", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "review_review_tasks",
        sa.Column("task_id", sa.String(length=26), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("priority", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "review_approvals",
        sa.Column("approval_id", sa.String(length=26), primary_key=True),
        sa.Column("task_id", sa.String(length=26), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("applied_changes_ref", sa.Text(), nullable=False),
        sa.Column("audit_event_id", sa.String(length=26), nullable=False),
    )
    op.create_table(
        "governance_policies",
        sa.Column("policy_id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("policy_type", sa.String(length=64), nullable=False),
        sa.Column("definition_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "audit_audit_events",
        sa.Column("audit_event_id", sa.String(length=26), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_json", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=26), nullable=False),
    )
    op.create_table(
        "audit_access_decisions",
        sa.Column("decision_id", sa.String(length=26), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("request_context_json", sa.JSON(), nullable=False),
        sa.Column("resources_json", sa.JSON(), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("applied_filters_json", sa.JSON(), nullable=False),
        sa.Column("applied_masks_json", sa.JSON(), nullable=False),
        sa.Column("audit_event_id", sa.String(length=26), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_access_decisions")
    op.drop_table("audit_audit_events")
    op.drop_table("governance_policies")
    op.drop_table("review_approvals")
    op.drop_table("review_review_tasks")
    op.drop_table("review_proposals")
    op.drop_index("ix_runs_runs_workspace_id", table_name="runs_runs")
    op.drop_table("runs_runs")
    op.drop_index("ix_catalog_datasets_workspace_id", table_name="catalog_datasets")
    op.drop_table("catalog_datasets")
    op.drop_index("ix_catalog_sources_workspace_id", table_name="catalog_sources")
    op.drop_table("catalog_sources")
    op.drop_table("workspaces")
