"""Scope scheduled-task idempotency to the authenticated owner session."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260803_0010"
down_revision: str | Sequence[str] | None = "20260803_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.drop_constraint("uq_scheduled_tasks_owner_idempotency", type_="unique")
        batch.create_unique_constraint(
            "uq_scheduled_tasks_owner_session_idempotency",
            ["owner_id", "owner_session_id", "idempotency_key_hash"],
        )


def downgrade() -> None:
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.drop_constraint("uq_scheduled_tasks_owner_session_idempotency", type_="unique")
        batch.create_unique_constraint(
            "uq_scheduled_tasks_owner_idempotency",
            ["owner_id", "idempotency_key_hash"],
        )
