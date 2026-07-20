"""harden action policy freshness and memory audit

Revision ID: 20260720_0008
Revises: 20260720_0007
Create Date: 2026-07-20 20:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0008"
down_revision: str | None = "20260720_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, length in (
        ("last_policy_decision", 50),
        ("last_policy_reason_code", 100),
        ("last_policy_reason", 500),
        ("last_required_role", 50),
        ("last_policy_campaign_status", 50),
        ("last_policy_workflow_status", 50),
    ):
        op.add_column(
            "agent_action_requests",
            sa.Column(name, sa.String(length=length), nullable=True),
        )
    op.add_column(
        "agent_action_requests",
        sa.Column("last_policy_revision_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "agent_action_requests",
        sa.Column(
            "last_policy_evaluated_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "agent_action_requests",
        sa.Column("approved_role", sa.String(length=50), nullable=True),
    )
    op.execute(
        """
        UPDATE agent_action_requests
        SET last_policy_decision = policy_decision,
            last_policy_reason_code = policy_reason_code,
            last_policy_reason = policy_reason,
            last_required_role = required_role,
            last_policy_evaluated_at = requested_at
        """
    )
    op.drop_constraint(
        "ck_action_requests_pending_consistency",
        "agent_action_requests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_requests_pending_consistency",
        "agent_action_requests",
        "status <> 'PENDING_APPROVAL' OR ((policy_decision = 'APPROVAL_REQUIRED' OR last_policy_decision = 'APPROVAL_REQUIRED') AND expires_at IS NOT NULL)",
    )

    for name, length in (
        ("reserved_campaign_status", 50),
        ("reserved_workflow_status", 50),
    ):
        op.add_column(
            "agent_action_executions",
            sa.Column(name, sa.String(length=length), nullable=True),
        )
    op.add_column(
        "agent_action_executions",
        sa.Column("reserved_campaign_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "agent_action_executions",
        sa.Column("reserved_revision_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "agent_action_executions",
        sa.Column(
            "memory_record_status",
            sa.String(length=50),
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
    )
    op.add_column(
        "agent_action_executions",
        sa.Column(
            "memory_record_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_action_executions",
        sa.Column("memory_record_error_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "agent_action_executions",
        sa.Column("memory_record_error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_action_executions",
        sa.Column("memory_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "agent_action_executions", "memory_record_status", server_default=None
    )
    op.alter_column(
        "agent_action_executions", "memory_record_attempts", server_default=None
    )
    op.create_check_constraint(
        "ck_action_executions_memory_attempts_nonnegative",
        "agent_action_executions",
        "memory_record_attempts >= 0",
    )
    op.create_check_constraint(
        "ck_action_executions_memory_recorded_at",
        "agent_action_executions",
        "memory_record_status <> 'RECORDED' OR memory_recorded_at IS NOT NULL",
    )

    op.add_column(
        "agent_memory_entries",
        sa.Column("action_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_memory_entries_action_execution",
        "agent_memory_entries",
        "agent_action_executions",
        ["action_execution_id"],
        ["action_execution_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_agent_memory_entries_action_execution_id",
        "agent_memory_entries",
        ["action_execution_id"],
    )
    op.create_unique_constraint(
        "uq_memory_entries_execution_event",
        "agent_memory_entries",
        ["action_execution_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_memory_entries_execution_event", "agent_memory_entries", type_="unique"
    )
    op.drop_index(
        "ix_agent_memory_entries_action_execution_id",
        table_name="agent_memory_entries",
    )
    op.drop_constraint(
        "fk_memory_entries_action_execution",
        "agent_memory_entries",
        type_="foreignkey",
    )
    op.drop_column("agent_memory_entries", "action_execution_id")

    op.drop_constraint(
        "ck_action_executions_memory_recorded_at",
        "agent_action_executions",
        type_="check",
    )
    op.drop_constraint(
        "ck_action_executions_memory_attempts_nonnegative",
        "agent_action_executions",
        type_="check",
    )
    for name in (
        "memory_recorded_at",
        "memory_record_error_message",
        "memory_record_error_code",
        "memory_record_attempts",
        "memory_record_status",
        "reserved_revision_number",
        "reserved_workflow_status",
        "reserved_campaign_version",
        "reserved_campaign_status",
    ):
        op.drop_column("agent_action_executions", name)

    op.drop_constraint(
        "ck_action_requests_pending_consistency",
        "agent_action_requests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_requests_pending_consistency",
        "agent_action_requests",
        "status <> 'PENDING_APPROVAL' OR (policy_decision = 'APPROVAL_REQUIRED' AND expires_at IS NOT NULL)",
    )
    for name in (
        "approved_role",
        "last_policy_evaluated_at",
        "last_policy_revision_number",
        "last_policy_workflow_status",
        "last_policy_campaign_status",
        "last_required_role",
        "last_policy_reason",
        "last_policy_reason_code",
        "last_policy_decision",
    ):
        op.drop_column("agent_action_requests", name)
