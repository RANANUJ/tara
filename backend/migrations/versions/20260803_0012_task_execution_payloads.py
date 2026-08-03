"""Add protected scheduled-task execution payloads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0012"
down_revision: str | Sequence[str] | None = "20260803_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_execution_payloads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("capability_id", sa.String(128), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("nonce", sa.LargeBinary(12), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(8192), nullable=False),
        sa.Column("binding_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["scheduled_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_task_execution_payloads_task"),
    )
    op.create_index("ix_task_execution_payloads_owner_task", "task_execution_payloads", ["owner_id", "task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_execution_payloads_owner_task", table_name="task_execution_payloads")
    op.drop_table("task_execution_payloads")
