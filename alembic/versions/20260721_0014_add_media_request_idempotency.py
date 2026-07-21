"""add media request idempotency

Revision ID: 20260721_0014
Revises: 0adb8d1b4a48
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0014"
down_revision: str | Sequence[str] | None = "0adb8d1b4a48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
    )
    op.create_unique_constraint(
        "uq_media_assets_actor_idempotency",
        "media_assets",
        ["created_by", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_media_assets_actor_idempotency", "media_assets", type_="unique"
    )
    op.drop_column("media_assets", "idempotency_key")
