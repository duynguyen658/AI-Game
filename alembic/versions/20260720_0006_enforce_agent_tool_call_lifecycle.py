"""enforce agent tool call lifecycle

Revision ID: 20260720_0006
Revises: 20260720_0005
Create Date: 2026-07-20 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260720_0006"
down_revision: str | None = "20260720_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_agent_tool_calls_completed_at_consistency",
        "agent_tool_calls",
        "(status IN ('COMPLETED', 'FAILED', 'REJECTED') AND completed_at IS NOT NULL) "
        "OR (status IN ('REQUESTED', 'RUNNING') AND completed_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_tool_calls_completed_at_consistency",
        "agent_tool_calls",
        type_="check",
    )
