"""Add the rebuildable structured-memory semantic-index outbox.

Revision ID: 20260802_0005
Revises: 20260801_0004
Create Date: 2026-08-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0005"
down_revision: str | Sequence[str] | None = "20260801_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_index_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("operation IN ('upsert', 'delete')", name="memory_index_operation"),
        sa.UniqueConstraint("memory_id", "operation", name="uq_memory_index_outbox_memory_operation"),
    )
    op.create_index("ix_memory_index_outbox_pending", "memory_index_outbox", ["processed_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_index_outbox_pending", table_name="memory_index_outbox")
    op.drop_table("memory_index_outbox")
