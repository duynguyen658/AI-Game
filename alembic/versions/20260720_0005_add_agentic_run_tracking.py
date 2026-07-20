"""add agentic run tracking

Revision ID: 20260720_0005
Revises: 20260720_0004
Create Date: 2026-07-20 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0005"
down_revision: str | None = "20260720_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("llm_call_count", sa.Integer(), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "iteration_count >= 0", name="ck_agent_runs_iteration_count_nonnegative"
        ),
        sa.CheckConstraint(
            "llm_call_count >= 0", name="ck_agent_runs_llm_call_count_nonnegative"
        ),
        sa.CheckConstraint(
            "tool_call_count >= 0", name="ck_agent_runs_tool_call_count_nonnegative"
        ),
        sa.CheckConstraint(
            "(status IN ('COMPLETED', 'FAILED', 'LIMIT_EXCEEDED') AND completed_at IS NOT NULL) "
            "OR (status IN ('CREATED', 'RUNNING') AND completed_at IS NULL)",
            name="ck_agent_runs_completed_at_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.campaign_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["workflow_runs.workflow_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("agent_run_id"),
    )
    op.create_index("ix_agent_runs_campaign_id", "agent_runs", ["campaign_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_workflow_id", "agent_runs", ["workflow_id"])
    op.create_index(
        "ix_agent_runs_workflow_started_at", "agent_runs", ["workflow_id", "started_at"]
    )
    op.create_index(
        "uq_agent_runs_one_active_specialist",
        "agent_runs",
        ["workflow_id", "agent_name"],
        unique=True,
        postgresql_where=sa.text("status IN ('CREATED', 'RUNNING')"),
    )

    op.create_table(
        "agent_tool_calls",
        sa.Column("tool_call_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_agent_tool_calls_duration_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.agent_run_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("tool_call_id"),
    )
    op.create_index(
        "ix_agent_tool_calls_agent_run_id", "agent_tool_calls", ["agent_run_id"]
    )
    op.create_index("ix_agent_tool_calls_status", "agent_tool_calls", ["status"])
    op.create_index(
        "ix_agent_tool_calls_run_started_at",
        "agent_tool_calls",
        ["agent_run_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_runs")
