"""add system evaluation mode and ownership

Revision ID: 20260721_0013
Revises: 20260721_0012
Create Date: 2026-07-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0013"
down_revision: str | None = "20260721_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_cases",
        sa.Column(
            "system_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("evaluation_cases", "actual_output", nullable=True)
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "execution_mode", sa.String(50), nullable=False, server_default="SNAPSHOT"
        ),
    )
    op.create_check_constraint(
        "ck_evaluation_runs_execution_mode",
        "evaluation_runs",
        "execution_mode IN ('SNAPSHOT', 'SYSTEM')",
    )
    for table_name, index_name in (
        ("campaigns", "ix_campaigns_evaluation_owner"),
        ("workflow_runs", "ix_workflow_runs_evaluation_owner"),
    ):
        op.add_column(
            table_name,
            sa.Column(
                "is_evaluation", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
        op.add_column(
            table_name,
            sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True)),
        )
        op.add_column(
            table_name,
            sa.Column("evaluation_case_id", postgresql.UUID(as_uuid=True)),
        )
        op.create_foreign_key(
            f"fk_{table_name}_evaluation_run_id",
            table_name,
            "evaluation_runs",
            ["evaluation_run_id"],
            ["evaluation_run_id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table_name}_evaluation_case_id",
            table_name,
            "evaluation_cases",
            ["evaluation_case_id"],
            ["evaluation_case_id"],
            ondelete="SET NULL",
        )
        op.create_index(index_name, table_name, ["is_evaluation", "evaluation_run_id"])


def downgrade() -> None:
    for table_name, index_name in (
        ("workflow_runs", "ix_workflow_runs_evaluation_owner"),
        ("campaigns", "ix_campaigns_evaluation_owner"),
    ):
        op.drop_index(index_name, table_name=table_name)
        op.drop_constraint(
            f"fk_{table_name}_evaluation_case_id", table_name, type_="foreignkey"
        )
        op.drop_constraint(
            f"fk_{table_name}_evaluation_run_id", table_name, type_="foreignkey"
        )
        op.drop_column(table_name, "evaluation_case_id")
        op.drop_column(table_name, "evaluation_run_id")
        op.drop_column(table_name, "is_evaluation")
    op.drop_constraint(
        "ck_evaluation_runs_execution_mode", "evaluation_runs", type_="check"
    )
    op.drop_column("evaluation_runs", "execution_mode")
    op.execute(
        "UPDATE evaluation_cases SET actual_output = '{}'::jsonb "
        "WHERE actual_output IS NULL"
    )
    op.alter_column("evaluation_cases", "actual_output", nullable=False)
    op.drop_column("evaluation_cases", "system_config")
