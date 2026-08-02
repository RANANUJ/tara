"""Add safe M16 task confirmation binding metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0008"
down_revision: str | Sequence[str] | None = "20260803_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.add_column(sa.Column("capability_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("target_summary", sa.String(256), nullable=True))
        batch.add_column(sa.Column("parameters_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("risk_level", sa.String(32), nullable=True))
        batch.add_column(sa.Column("confirmation_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("confirmation_status", sa.String(32), nullable=True))
        batch.add_column(sa.Column("confirmation_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("confirmation_binding_hash", sa.String(64), nullable=True))
    op.create_index("ix_scheduled_tasks_confirmation", "scheduled_tasks", ["owner_id", "confirmation_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_confirmation", table_name="scheduled_tasks")
    with op.batch_alter_table("scheduled_tasks") as batch:
        for name in ("confirmation_binding_hash", "confirmation_expires_at", "confirmation_status", "confirmation_id", "risk_level", "parameters_hash", "target_summary", "capability_id"):
            batch.drop_column(name)
