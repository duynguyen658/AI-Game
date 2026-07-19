"""initial backend tables

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("game_name", sa.String(length=200), nullable=False),
        sa.Column("genre", sa.String(length=100), nullable=False),
        sa.Column("target_audience", sa.String(length=300), nullable=False),
        sa.Column("market", sa.String(length=100), nullable=False),
        sa.Column("platforms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("campaign_objective", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=500), nullable=False),
        sa.Column("launch_date", sa.Date(), nullable=False),
        sa.Column("promotion", sa.Text(), nullable=False),
        sa.Column("raw_brief", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "brief_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "generated_content", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "quality_review", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_campaign_quality_score_range",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_campaign_retry_count_nonnegative",
        ),
        sa.CheckConstraint("version >= 1", name="ck_campaign_version_positive"),
        sa.PrimaryKeyConstraint("campaign_id"),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_quality_score", "campaigns", ["quality_score"])
    op.create_index(
        "ix_campaigns_status_created_at",
        "campaigns",
        ["status", "created_at"],
    )

    op.create_table(
        "workflow_runs",
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_step", sa.String(length=50), nullable=False),
        sa.Column("llm_call_count", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "llm_call_count >= 0",
            name="ck_workflow_llm_call_count_nonnegative",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="ck_workflow_quality_score_range",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_workflow_retry_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.campaign_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("workflow_id"),
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_campaign_id", "workflow_runs", ["campaign_id"])
    op.create_index(
        "ix_workflow_runs_campaign_status",
        "workflow_runs",
        ["campaign_id", "status"],
    )

    op.create_table(
        "approval_records",
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=50), nullable=False),
        sa.Column("feedback", sa.String(length=5000), nullable=True),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "previous_version >= 1",
            name="ck_approval_previous_version_positive",
        ),
        sa.CheckConstraint(
            "resulting_version >= previous_version",
            name="ck_approval_version_order",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.campaign_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["workflow_runs.workflow_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("approval_id"),
        sa.UniqueConstraint(
            "workflow_id", "decision", name="uq_approval_workflow_decision"
        ),
    )
    op.create_index(
        "ix_approval_records_workflow_id", "approval_records", ["workflow_id"]
    )
    op.create_index(
        "ix_approval_records_campaign_id", "approval_records", ["campaign_id"]
    )
    op.create_index(
        "ix_approval_records_campaign_decided_at",
        "approval_records",
        ["campaign_id", "decided_at"],
    )

    op.create_table(
        "security_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=True),
        sa.Column("ip_address", sa.String(length=100), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.String(length=200), nullable=True),
        sa.Column("campaign_id", sa.String(length=100), nullable=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_severity", "security_events", ["severity"])
    op.create_index("ix_security_events_actor_id", "security_events", ["actor_id"])
    op.create_index(
        "ix_security_events_type_created_at",
        "security_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_security_events_actor_created_at",
        "security_events",
        ["actor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_events_actor_created_at", table_name="security_events")
    op.drop_index("ix_security_events_type_created_at", table_name="security_events")
    op.drop_index("ix_security_events_actor_id", table_name="security_events")
    op.drop_index("ix_security_events_severity", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_table("security_events")

    op.drop_index(
        "ix_approval_records_campaign_decided_at", table_name="approval_records"
    )
    op.drop_index("ix_approval_records_campaign_id", table_name="approval_records")
    op.drop_index("ix_approval_records_workflow_id", table_name="approval_records")
    op.drop_table("approval_records")

    op.drop_index("ix_workflow_runs_campaign_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_campaign_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index("ix_campaigns_status_created_at", table_name="campaigns")
    op.drop_index("ix_campaigns_quality_score", table_name="campaigns")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
