"""enforce workflow and approval invariants

Revision ID: 20260720_0002
Revises: 20260720_0001
Create Date: 2026-07-20 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0002"
down_revision: str | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_STATUS_SQL = (
    "'RECEIVED', "
    "'VALIDATING', "
    "'NEEDS_CLARIFICATION', "
    "'ANALYZING', "
    "'GENERATING', "
    "'REVIEWING', "
    "'MANUAL_REVIEW_REQUIRED', "
    "'PENDING_APPROVAL', "
    "'REVISION_REQUIRED'"
)


def upgrade() -> None:
    op.drop_constraint(
        "uq_approval_workflow_decision",
        "approval_records",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_approval_records_workflow_id",
        "approval_records",
        ["workflow_id"],
    )
    op.create_index(
        "uq_workflow_runs_one_active_per_campaign",
        "workflow_runs",
        ["campaign_id"],
        unique=True,
        postgresql_where=sa.text(
            f"completed_at IS NULL AND status IN ({ACTIVE_STATUS_SQL})"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_workflow_runs_one_active_per_campaign",
        table_name="workflow_runs",
    )
    op.drop_constraint(
        "uq_approval_records_workflow_id",
        "approval_records",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_approval_workflow_decision",
        "approval_records",
        ["workflow_id", "decision"],
    )
