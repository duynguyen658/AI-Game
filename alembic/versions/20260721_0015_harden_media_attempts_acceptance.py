"""harden media attempts and acceptance semantics

Revision ID: 20260721_0015
Revises: b6a097aa4b4d
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260721_0015"
down_revision: str | None = "b6a097aa4b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_generation_attempts", sa.Column("job_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "media_generation_attempts",
        sa.Column("worker_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "media_generation_attempts",
        sa.Column("job_attempt_number", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_media_attempts_job_id",
        "media_generation_attempts",
        "background_jobs",
        ["job_id"],
        ["job_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_media_attempts_job_status",
        "media_generation_attempts",
        ["job_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_media_attempts_asset_status",
        "media_generation_attempts",
        ["media_asset_id", "status"],
        unique=False,
    )
    op.execute(
        """
        UPDATE media_generation_attempts
        SET status = 'FAILED',
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            error_code = COALESCE(error_code, 'MIGRATION_ORPHANED_ATTEMPT'),
            error_message = COALESCE(error_message, 'Active attempt was terminalized')
        WHERE status = 'STARTED'
        """
    )
    op.create_check_constraint(
        "ck_media_attempt_status",
        "media_generation_attempts",
        "status IN ('STARTED', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.create_check_constraint(
        "ck_media_attempt_job_number_positive",
        "media_generation_attempts",
        "job_attempt_number IS NULL OR job_attempt_number > 0",
    )

    op.add_column(
        "ai_task_impacts",
        sa.Column(
            "task_completed_successfully",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column(
        "ai_task_impacts",
        "output_accepted",
        existing_type=sa.Boolean(),
        nullable=True,
    )
    op.add_column(
        "user_feedback", sa.Column("output_accepted", sa.Boolean(), nullable=True)
    )
    op.execute(
        "UPDATE ai_task_impacts SET output_accepted = NULL, accepted_without_editing = false"
    )
    op.create_check_constraint(
        "ck_ai_task_impact_first_pass_acceptance",
        "ai_task_impacts",
        "NOT accepted_without_editing OR "
        "(output_accepted IS TRUE AND editing_minutes = 0 AND rework_count = 0)",
    )
    op.create_check_constraint(
        "ck_user_feedback_first_pass_acceptance",
        "user_feedback",
        "NOT accepted_without_editing OR "
        "(output_accepted IS TRUE AND editing_minutes = 0 AND rework_count = 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_feedback_first_pass_acceptance", "user_feedback", type_="check"
    )
    op.drop_constraint(
        "ck_ai_task_impact_first_pass_acceptance", "ai_task_impacts", type_="check"
    )
    op.execute(
        "UPDATE ai_task_impacts SET output_accepted = false WHERE output_accepted IS NULL"
    )
    op.alter_column(
        "ai_task_impacts",
        "output_accepted",
        existing_type=sa.Boolean(),
        nullable=False,
    )
    op.drop_column("user_feedback", "output_accepted")
    op.drop_column("ai_task_impacts", "task_completed_successfully")

    op.drop_constraint(
        "ck_media_attempt_job_number_positive",
        "media_generation_attempts",
        type_="check",
    )
    op.drop_constraint(
        "ck_media_attempt_status", "media_generation_attempts", type_="check"
    )
    op.drop_index(
        "ix_media_attempts_asset_status", table_name="media_generation_attempts"
    )
    op.drop_index(
        "ix_media_attempts_job_status", table_name="media_generation_attempts"
    )
    op.drop_constraint(
        "fk_media_attempts_job_id", "media_generation_attempts", type_="foreignkey"
    )
    op.drop_column("media_generation_attempts", "job_attempt_number")
    op.drop_column("media_generation_attempts", "worker_id")
    op.drop_column("media_generation_attempts", "job_id")
