"""Bind confirmations to the authenticated owner session that created them.

Revision ID: 20260801_0003
Revises: 20260801_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0003"
down_revision: str | Sequence[str] | None = "20260801_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pending_confirmations", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("owner_session_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_pending_confirmations_owner", "owners", ["owner_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key(
            "fk_pending_confirmations_owner_session",
            "owner_sessions",
            ["owner_session_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_pending_confirmations_owner_session_status_expires",
        "pending_confirmations",
        ["owner_id", "owner_session_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pending_confirmations_owner_session_status_expires", table_name="pending_confirmations")
    with op.batch_alter_table("pending_confirmations", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_pending_confirmations_owner_session", type_="foreignkey")
        batch_op.drop_constraint("fk_pending_confirmations_owner", type_="foreignkey")
        batch_op.drop_column("owner_session_id")
        batch_op.drop_column("owner_id")
