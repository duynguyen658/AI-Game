"""add background jobs and worker heartbeats

Revision ID: 20260721_0009
Revises: 20260720_0008
Create Date: 2026-07-21 00:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0009"
down_revision: str | None = "20260720_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_background_jobs_attempt_nonnegative"
        ),
        sa.CheckConstraint(
            "max_attempts > 0", name="ck_background_jobs_max_attempts_positive"
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name="ck_background_jobs_priority_range",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency"),
    )
    op.create_index(
        "ix_background_jobs_lease_order",
        "background_jobs",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "ix_background_jobs_lease_expiry",
        "background_jobs",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_background_jobs_type_created",
        "background_jobs",
        ["job_type", "created_at"],
    )

    op.create_table(
        "job_attempts",
        sa.Column(
            "job_attempt_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("background_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="RUNNING"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "attempt_number > 0", name="ck_job_attempts_number_positive"
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_job_attempts_duration_nonnegative",
        ),
        sa.UniqueConstraint(
            "job_id", "attempt_number", name="uq_job_attempts_job_number"
        ),
    )
    op.create_index(
        "ix_job_attempts_job_started",
        "job_attempts",
        ["job_id", "started_at"],
    )

    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=200), primary_key=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("current_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_worker_heartbeats_last_seen_at",
        "worker_heartbeats",
        ["last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_last_seen_at", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
    op.drop_index("ix_job_attempts_job_started", table_name="job_attempts")
    op.drop_table("job_attempts")
    op.drop_index("ix_background_jobs_type_created", table_name="background_jobs")
    op.drop_index("ix_background_jobs_lease_expiry", table_name="background_jobs")
    op.drop_index("ix_background_jobs_lease_order", table_name="background_jobs")
    op.drop_table("background_jobs")
