"""Add safe target identity hash to scheduled tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0009"
down_revision: str | Sequence[str] | None = "20260803_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.add_column(sa.Column("target_identity_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.drop_column("target_identity_hash")
