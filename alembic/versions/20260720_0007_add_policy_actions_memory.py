"""add policy actions and structured memory

Revision ID: 20260720_0007
Revises: 20260720_0006
Create Date: 2026-07-20 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0007"
down_revision: str | None = "20260720_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_action_requests",
        sa.Column("action_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("action_name", sa.String(length=100), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rationale_summary", sa.Text(), nullable=False),
        sa.Column("policy_decision", sa.String(length=50), nullable=False),
        sa.Column("policy_reason_code", sa.String(length=100), nullable=False),
        sa.Column("policy_reason", sa.String(length=500), nullable=False),
        sa.Column("required_role", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(length=200), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_action_requests_version_positive"),
        sa.CheckConstraint(
            "policy_decision <> 'FORBIDDEN' OR status = 'REJECTED'",
            name="ck_action_requests_forbidden_rejected",
        ),
        sa.CheckConstraint(
            "status <> 'PENDING_APPROVAL' OR (policy_decision = 'APPROVAL_REQUIRED' AND expires_at IS NOT NULL)",
            name="ck_action_requests_pending_consistency",
        ),
        sa.CheckConstraint(
            "status <> 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_action_requests_approved_consistency",
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR rejected_at IS NOT NULL",
            name="ck_action_requests_rejected_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.agent_run_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["workflow_runs.workflow_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.campaign_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("action_request_id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_action_requests_idempotency_key"
        ),
    )
    op.create_index(
        "ix_agent_action_requests_agent_run_id",
        "agent_action_requests",
        ["agent_run_id"],
    )
    op.create_index(
        "ix_agent_action_requests_workflow_id",
        "agent_action_requests",
        ["workflow_id"],
    )
    op.create_index(
        "ix_agent_action_requests_campaign_id",
        "agent_action_requests",
        ["campaign_id"],
    )
    op.create_index(
        "ix_agent_action_requests_action_name",
        "agent_action_requests",
        ["action_name"],
    )
    op.create_index(
        "ix_agent_action_requests_status", "agent_action_requests", ["status"]
    )
    op.create_index(
        "ix_action_requests_campaign_requested",
        "agent_action_requests",
        ["campaign_id", "requested_at"],
    )
    op.create_index(
        "ix_action_requests_workflow_requested",
        "agent_action_requests",
        ["workflow_id", "requested_at"],
    )
    op.create_index(
        "ix_action_requests_pending",
        "agent_action_requests",
        ["status", "expires_at"],
        postgresql_where=sa.text("status = 'PENDING_APPROVAL'"),
    )

    op.create_table(
        "agent_action_executions",
        sa.Column("action_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_action_executions_attempt_positive"
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_action_executions_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "(status = 'CREATED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'FAILED', 'CANCELLED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_action_executions_status_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["action_request_id"],
            ["agent_action_requests.action_request_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("action_execution_id"),
        sa.UniqueConstraint(
            "action_request_id", name="uq_action_executions_one_per_request"
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_action_executions_idempotency_key"
        ),
    )
    op.create_index(
        "ix_agent_action_executions_action_request_id",
        "agent_action_executions",
        ["action_request_id"],
    )
    op.create_index(
        "ix_agent_action_executions_status", "agent_action_executions", ["status"]
    )
    op.create_index(
        "ix_action_executions_request_created",
        "agent_action_executions",
        ["action_request_id", "created_at"],
    )

    op.create_table(
        "agent_memory_entries",
        sa.Column("memory_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.String(length=100), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "importance >= 1 AND importance <= 5",
            name="ck_memory_entries_importance_range",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_memory_entries_expiration_order",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.campaign_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"], ["workflow_runs.workflow_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["agent_runs.agent_run_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["action_request_id"],
            ["agent_action_requests.action_request_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("memory_entry_id"),
    )
    for column in (
        "campaign_id",
        "workflow_id",
        "agent_run_id",
        "action_request_id",
        "event_type",
    ):
        op.create_index(
            f"ix_agent_memory_entries_{column}", "agent_memory_entries", [column]
        )
    op.create_index(
        "ix_memory_entries_campaign_created",
        "agent_memory_entries",
        ["campaign_id", "created_at"],
    )
    op.create_index(
        "ix_memory_entries_workflow_created",
        "agent_memory_entries",
        ["workflow_id", "created_at"],
    )
    op.create_index(
        "ix_memory_entries_event_created",
        "agent_memory_entries",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_memory_entries_importance_created",
        "agent_memory_entries",
        ["importance", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("agent_memory_entries")
    op.drop_table("agent_action_executions")
    op.drop_table("agent_action_requests")
