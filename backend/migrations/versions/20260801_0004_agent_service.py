"""Add owner-scoped conversation and content-minimized agent request metadata.

Revision ID: 20260801_0004
Revises: 20260801_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0004"
down_revision: str | Sequence[str] | None = "20260801_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_conversations_owner", "owners", ["owner_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_conversations_owner_created", "conversations", ["owner_id", "created_at"])
    op.create_table(
        "agent_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_transcript_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("route_category", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column("model_identifier", sa.String(length=256), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["owner_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "session_id", "idempotency_key_hash", name="uq_agent_requests_owner_session_idempotency"),
    )
    op.create_index("ix_agent_requests_owner_session_status", "agent_requests", ["owner_id", "session_id", "status"])
    op.create_index("ix_agent_requests_conversation_created", "agent_requests", ["conversation_id", "created_at"])
    with op.batch_alter_table("conversation_turns", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("agent_request_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("safe_metadata", sa.JSON(), nullable=True))
        batch_op.create_foreign_key("fk_conversation_turns_agent_request", "agent_requests", ["agent_request_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("conversation_turns", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_conversation_turns_agent_request", type_="foreignkey")
        batch_op.drop_column("safe_metadata")
        batch_op.drop_column("agent_request_id")
    op.drop_index("ix_agent_requests_conversation_created", table_name="agent_requests")
    op.drop_index("ix_agent_requests_owner_session_status", table_name="agent_requests")
    op.drop_table("agent_requests")
    op.drop_index("ix_conversations_owner_created", table_name="conversations")
    with op.batch_alter_table("conversations", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_conversations_owner", type_="foreignkey")
        batch_op.drop_column("owner_id")
