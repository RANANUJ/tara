"""Create M16 owner-scoped scheduled tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0007"
down_revision: str | Sequence[str] | None = "20260802_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("owner_session_id", sa.Uuid(), nullable=True), sa.Column("title", sa.String(160), nullable=False),
        sa.Column("task_kind", sa.String(32), nullable=False), sa.Column("instruction", sa.String(1024), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False), sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("state", sa.String(32), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True), sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(64), nullable=True), sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["owner_session_id"], ["owner_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("owner_id", "idempotency_key_hash", name="uq_scheduled_tasks_owner_idempotency"),
    )
    op.create_index("ix_scheduled_tasks_due", "scheduled_tasks", ["enabled", "state", "next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_due", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
