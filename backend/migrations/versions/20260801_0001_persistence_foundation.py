"""Create the M2 foundational persistence schema.

Revision ID: 20260801_0001
Revises:
Create Date: 2026-08-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260801_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_column(name: str = "id", *, primary_key: bool = False) -> sa.Column[sa.UUID]:
    return sa.Column(name, sa.Uuid(), primary_key=primary_key, nullable=not primary_key)


def _timestamps() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "conversations",
        _uuid_column(primary_key=True),
        sa.Column("label", sa.String(length=256), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "structured_memories",
        _uuid_column(primary_key=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_reference", sa.String(length=256), nullable=True),
        sa.Column("retention_category", sa.String(length=64), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "category IN ('preference', 'fact', 'task', 'conversation_summary')",
            name="memory_category",
        ),
        sa.CheckConstraint(
            "source IN ('user', 'conversation', 'consolidation', 'import')",
            name="memory_source",
        ),
        sa.CheckConstraint(
            "retention_category IN ('preference', 'task', 'casual')",
            name="retention_category",
        ),
    )
    op.create_index(
        "ix_structured_memories_retention_cleanup",
        "structured_memories",
        ["retention_category", "pinned", "expires_at"],
    )
    op.create_index(
        "ix_structured_memories_category_created", "structured_memories", ["category", "created_at"]
    )
    op.create_table(
        "permission_settings",
        _uuid_column(primary_key=True),
        sa.Column("capability", sa.String(length=128), nullable=False),
        sa.Column("grant_state", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("grant_state IN ('enabled', 'disabled')", name="permission_grant_state"),
        sa.UniqueConstraint("capability", name="uq_permission_settings_capability"),
    )
    op.create_table(
        "audit_events",
        _uuid_column(primary_key=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_reference", sa.String(length=256), nullable=True),
        sa.Column("subject_reference", sa.String(length=256), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_events_occurred", "audit_events", ["occurred_at"])
    op.create_table(
        "scheduler_job_metadata",
        _uuid_column(primary_key=True),
        sa.Column("job_key", sa.String(length=128), nullable=False),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=64), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "last_status IN ('scheduled', 'succeeded', 'failed', 'disabled')",
            name="scheduler_job_status",
        ),
        sa.UniqueConstraint("job_key", name="uq_scheduler_job_metadata_job_key"),
    )
    op.create_index(
        "ix_scheduler_job_metadata_next_run", "scheduler_job_metadata", ["enabled", "next_run_at"]
    )
    op.create_table(
        "safe_service_configurations",
        _uuid_column(primary_key=True),
        sa.Column("config_key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("config_key", name="uq_safe_service_configurations_key"),
    )
    op.create_table(
        "conversation_turns",
        _uuid_column(primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="conversation_turn_role"),
        sa.CheckConstraint(
            "status IN ('pending', 'streaming', 'completed', 'cancelled', 'failed')",
            name="conversation_turn_status",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_conversation_turns_conversation_sequence"),
    )
    op.create_index(
        "ix_conversation_turns_conversation_created",
        "conversation_turns",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "pending_confirmations",
        _uuid_column(primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("permission_setting_id", sa.Uuid(), nullable=True),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("action_summary", sa.Text(), nullable=False),
        sa.Column("action_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('proposed', 'awaiting_confirmation', 'rejected_by_policy', 'rejected', "
            "'expired', 'invalidated', 'approved', 'executing', 'succeeded', 'failed', 'uncertain')",
            name="confirmation_status",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["permission_setting_id"], ["permission_settings.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_pending_confirmations_status_expires", "pending_confirmations", ["status", "expires_at"]
    )
    op.create_table(
        "confirmation_consumptions",
        _uuid_column(primary_key=True),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=128), nullable=True),
        sa.Column("audit_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'expired')", name="confirmation_decision"
        ),
        sa.ForeignKeyConstraint(["confirmation_id"], ["pending_confirmations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("confirmation_id", name="uq_confirmation_consumptions_confirmation"),
    )


def downgrade() -> None:
    op.drop_table("confirmation_consumptions")
    op.drop_index("ix_pending_confirmations_status_expires", table_name="pending_confirmations")
    op.drop_table("pending_confirmations")
    op.drop_index("ix_conversation_turns_conversation_created", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_table("safe_service_configurations")
    op.drop_index("ix_scheduler_job_metadata_next_run", table_name="scheduler_job_metadata")
    op.drop_table("scheduler_job_metadata")
    op.drop_index("ix_audit_events_occurred", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("permission_settings")
    op.drop_index("ix_structured_memories_category_created", table_name="structured_memories")
    op.drop_index("ix_structured_memories_retention_cleanup", table_name="structured_memories")
    op.drop_table("structured_memories")
    op.drop_table("conversations")
