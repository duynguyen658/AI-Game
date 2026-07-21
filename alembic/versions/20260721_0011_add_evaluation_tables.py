"""add evaluation datasets cases runs and results

Revision ID: 20260721_0011
Revises: 20260721_0010
Create Date: 2026-07-21 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0011"
down_revision: str | None = "20260721_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "name", "version", name="uq_evaluation_datasets_name_version"
        ),
    )
    op.create_index(
        "ix_evaluation_datasets_created",
        "evaluation_datasets",
        ["created_at", "dataset_id"],
    )
    op.create_table(
        "evaluation_cases",
        sa.Column(
            "evaluation_case_id", postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_datasets.dataset_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("case_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("campaign_input", postgresql.JSONB(), nullable=False),
        sa.Column("actual_output", postgresql.JSONB(), nullable=False),
        sa.Column("expected", postgresql.JSONB(), nullable=False),
        sa.Column(
            "thresholds",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "case_order >= 0", name="ck_evaluation_cases_order_nonnegative"
        ),
        sa.UniqueConstraint(
            "dataset_id", "name", name="uq_evaluation_cases_dataset_name"
        ),
    )
    op.create_index(
        "ix_evaluation_cases_dataset_order",
        "evaluation_cases",
        ["dataset_id", "case_order"],
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_datasets.dataset_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_configuration_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("tool_registry_version", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("application_version", sa.String(100), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("regression_passed", sa.Boolean()),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.String(2000)),
        sa.CheckConstraint(
            "total_cases >= 0", name="ck_evaluation_runs_total_nonnegative"
        ),
        sa.CheckConstraint(
            "completed_cases >= 0", name="ck_evaluation_runs_completed_nonnegative"
        ),
    )
    op.create_index(
        "ix_evaluation_runs_status_created", "evaluation_runs", ["status", "created_at"]
    )
    op.create_index(
        "ix_evaluation_runs_dataset_created",
        "evaluation_runs",
        ["dataset_id", "created_at"],
    )
    op.create_table(
        "evaluation_results",
        sa.Column(
            "evaluation_result_id", postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column(
            "evaluation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_runs.evaluation_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_cases.evaluation_case_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="ERROR"),
        sa.Column(
            "assertions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("output_summary", sa.String(1000)),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.String(2000)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "duration_ms >= 0", name="ck_evaluation_results_duration_nonnegative"
        ),
        sa.CheckConstraint(
            "input_tokens >= 0", name="ck_evaluation_results_input_tokens_nonnegative"
        ),
        sa.CheckConstraint(
            "output_tokens >= 0", name="ck_evaluation_results_output_tokens_nonnegative"
        ),
        sa.CheckConstraint(
            "estimated_cost >= 0", name="ck_evaluation_results_cost_nonnegative"
        ),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            name="uq_evaluation_results_run_case",
        ),
    )
    op.create_index(
        "ix_evaluation_results_run_status",
        "evaluation_results",
        ["evaluation_run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_run_status", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_dataset_created", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status_created", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_dataset_order", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index("ix_evaluation_datasets_created", table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")
