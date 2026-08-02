"""Add explicit task status to structured task memories.

Revision ID: 20260802_0006
Revises: 20260802_0005
Create Date: 2026-08-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0006"
down_revision: str | Sequence[str] | None = "20260802_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("structured_memories", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("task_status", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint("memory_task_status", "task_status IS NULL OR task_status IN ('open', 'completed', 'cancelled')")


def downgrade() -> None:
    with op.batch_alter_table("structured_memories", recreate="always") as batch_op:
        batch_op.drop_constraint("memory_task_status", type_="check")
        batch_op.drop_column("task_status")
