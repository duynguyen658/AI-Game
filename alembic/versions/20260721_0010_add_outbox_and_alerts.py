"""add transactional outbox and operational alerts

Revision ID: 20260721_0010
Revises: 20260721_0009
Create Date: 2026-07-21 00:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0010"
down_revision: str | None = "20260721_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column(
            "outbox_event_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=200), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="PENDING"
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_outbox_events_attempt_nonnegative"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency"),
    )
    op.create_index(
        "ix_outbox_events_dispatch",
        "outbox_events",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_outbox_events_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id"],
    )
    op.create_index("ix_outbox_events_locked", "outbox_events", ["status", "locked_at"])

    op.create_table(
        "operational_alerts",
        sa.Column(
            "alert_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("alert_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="OPEN"
        ),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=200), nullable=False),
        sa.Column("deduplication_key", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("acknowledged_by", sa.String(length=200), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "occurrence_count > 0", name="ck_operational_alerts_occurrence_positive"
        ),
        sa.UniqueConstraint("deduplication_key", name="uq_operational_alerts_dedup"),
    )
    op.create_index(
        "ix_operational_alerts_status_seen",
        "operational_alerts",
        ["status", "last_seen_at"],
    )
    op.create_index(
        "ix_operational_alerts_type_seen",
        "operational_alerts",
        ["alert_type", "last_seen_at"],
    )
    op.create_index(
        "ix_operational_alerts_resource",
        "operational_alerts",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_operational_alerts_resource", table_name="operational_alerts")
    op.drop_index("ix_operational_alerts_type_seen", table_name="operational_alerts")
    op.drop_index("ix_operational_alerts_status_seen", table_name="operational_alerts")
    op.drop_table("operational_alerts")
    op.drop_index("ix_outbox_events_locked", table_name="outbox_events")
    op.drop_index("ix_outbox_events_aggregate", table_name="outbox_events")
    op.drop_index("ix_outbox_events_dispatch", table_name="outbox_events")
    op.drop_table("outbox_events")
