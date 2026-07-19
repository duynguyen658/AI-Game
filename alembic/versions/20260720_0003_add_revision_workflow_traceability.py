"""add revision workflow traceability

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0003"
down_revision: str | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("parent_workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "workflow_runs",
        sa.Column(
            "revision_number",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_foreign_key(
        "fk_workflow_runs_parent_workflow_id",
        "workflow_runs",
        "workflow_runs",
        ["parent_workflow_id"],
        ["workflow_id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_workflow_revision_nonnegative",
        "workflow_runs",
        "revision_number >= 0",
    )
    op.create_index(
        "ix_workflow_runs_parent_workflow_id",
        "workflow_runs",
        ["parent_workflow_id"],
    )
    op.alter_column("workflow_runs", "revision_number", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_parent_workflow_id", table_name="workflow_runs")
    op.drop_constraint(
        "ck_workflow_revision_nonnegative",
        "workflow_runs",
        type_="check",
    )
    op.drop_constraint(
        "fk_workflow_runs_parent_workflow_id",
        "workflow_runs",
        type_="foreignkey",
    )
    op.drop_column("workflow_runs", "revision_number")
    op.drop_column("workflow_runs", "parent_workflow_id")
