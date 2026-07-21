"""harden outbox leases with expiry heartbeat and fencing

Revision ID: 20260721_0012
Revises: 20260721_0011
Create Date: 2026-07-21 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0012"
down_revision: str | None = "20260721_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "outbox_events",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "outbox_events",
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_outbox_events_lease_expiry",
        "outbox_events",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_lease_expiry", table_name="outbox_events")
    op.drop_column("outbox_events", "lease_version")
    op.drop_column("outbox_events", "last_heartbeat_at")
    op.drop_column("outbox_events", "lease_expires_at")
