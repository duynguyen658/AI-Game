"""add campaign ownership for resource authorization

Revision ID: 20260722_0016
Revises: 20260721_0015
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260722_0016"
down_revision: str | None = "20260721_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "created_by",
            sa.String(length=200),
            nullable=False,
            server_default="legacy-system",
        ),
    )
    op.alter_column("campaigns", "created_by", server_default=None)
    op.create_index(
        "ix_campaigns_owner_created_at",
        "campaigns",
        ["created_by", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_campaigns_owner_created_at", table_name="campaigns")
    op.drop_column("campaigns", "created_by")
