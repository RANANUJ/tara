"""Add safe M16 task claims and execution-run metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0011"
down_revision: str | Sequence[str] | None = "20260803_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.add_column(sa.Column("claim_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_scheduled_tasks_claim", "scheduled_tasks", ["claim_id", "claim_expires_at"])
    op.create_table(
        "scheduled_task_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("outcome_code", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["scheduled_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "run_id", name="uq_scheduled_task_runs_task_run"),
    )
    op.create_index("ix_scheduled_task_runs_task_scheduled", "scheduled_task_runs", ["task_id", "scheduled_for"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_task_runs_task_scheduled", table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")
    op.drop_index("ix_scheduled_tasks_claim", table_name="scheduled_tasks")
    with op.batch_alter_table("scheduled_tasks") as batch:
        batch.drop_column("claim_expires_at")
        batch.drop_column("claimed_at")
        batch.drop_column("claim_id")
