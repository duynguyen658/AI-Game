"""rename revision number check constraint

Revision ID: 20260720_0004
Revises: 20260720_0003
Create Date: 2026-07-20 05:45:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260720_0004"
down_revision: str | None = "20260720_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CONSTRAINT = "ck_workflow_revision_nonnegative"
NEW_CONSTRAINT = "ck_workflow_runs_revision_number_non_negative"


def upgrade() -> None:
    op.drop_constraint(
        OLD_CONSTRAINT,
        "workflow_runs",
        type_="check",
    )
    op.create_check_constraint(
        NEW_CONSTRAINT,
        "workflow_runs",
        "revision_number >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        NEW_CONSTRAINT,
        "workflow_runs",
        type_="check",
    )
    op.create_check_constraint(
        OLD_CONSTRAINT,
        "workflow_runs",
        "revision_number >= 0",
    )
