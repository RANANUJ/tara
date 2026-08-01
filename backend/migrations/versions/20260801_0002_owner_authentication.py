"""Create single-owner account and opaque session tables.

Revision ID: 20260801_0002
Revises: 20260801_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0002"
down_revision: str | Sequence[str] | None = "20260801_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_slot", sa.Integer(), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("owner_slot = 1", name="ck_owners_singleton_slot"),
        sa.UniqueConstraint("owner_slot", name="uq_owners_singleton_slot"),
    )
    op.create_table(
        "owner_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_label", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_owner_sessions_token_hash"),
    )
    op.create_index("ix_owner_sessions_owner_active", "owner_sessions", ["owner_id", "revoked_at", "expires_at"])
    op.create_index("ix_owner_sessions_expiry", "owner_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_owner_sessions_expiry", table_name="owner_sessions")
    op.drop_index("ix_owner_sessions_owner_active", table_name="owner_sessions")
    op.drop_table("owner_sessions")
    op.drop_table("owners")
