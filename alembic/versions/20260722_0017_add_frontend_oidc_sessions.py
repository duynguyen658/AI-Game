"""add opaque frontend OIDC sessions

Revision ID: 20260722_0017
Revises: 20260722_0016
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260722_0017"
down_revision: str | None = "20260722_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "frontend_oidc_sessions",
        sa.Column("session_id_hash", sa.String(length=64), primary_key=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column(
            "access_token_expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("refresh_owner_hash", sa.String(length=64)),
        sa.Column("refresh_started_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "char_length(session_id_hash) = 64",
            name="ck_frontend_oidc_session_hash_length",
        ),
        sa.CheckConstraint(
            "session_version >= 1",
            name="ck_frontend_oidc_session_version_positive",
        ),
        sa.CheckConstraint(
            "session_expires_at > created_at",
            name="ck_frontend_oidc_session_expiry_order",
        ),
        sa.CheckConstraint(
            "(refresh_owner_hash IS NULL) = (refresh_started_at IS NULL)",
            name="ck_frontend_oidc_refresh_lease_consistency",
        ),
    )
    op.create_index(
        "ix_frontend_oidc_sessions_expiry",
        "frontend_oidc_sessions",
        ["session_expires_at"],
    )
    op.create_index(
        "ix_frontend_oidc_sessions_revoked",
        "frontend_oidc_sessions",
        ["revoked_at"],
        postgresql_where=sa.text("revoked_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_frontend_oidc_sessions_revoked", table_name="frontend_oidc_sessions"
    )
    op.drop_index(
        "ix_frontend_oidc_sessions_expiry", table_name="frontend_oidc_sessions"
    )
    op.drop_table("frontend_oidc_sessions")
