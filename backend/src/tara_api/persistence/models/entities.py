"""Foundational ORM entities for the M2 local SQLite persistence layer."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from tara_api.persistence.models.base import Base, UTCDateTime
from tara_api.persistence.types import (
    ConfirmationDecision,
    ConfirmationStatus,
    ConversationTurnRole,
    ConversationTurnStatus,
    MemoryCategory,
    MemorySource,
    PermissionGrantState,
    RetentionCategory,
    SchedulerJobStatus,
    utc_now,
)


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def _enum_type(enum_class: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=_enum_values,
    )


class TimestampedModel:
    """Common immutable creation and mutable update timestamps."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ConversationModel(TimestampedModel, Base):
    """Internal durable conversation metadata."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="SET NULL"), nullable=True)


class AgentRequestModel(TimestampedModel, Base):
    """Internal, content-minimized M9C request identity and lifecycle metadata."""

    __tablename__ = "agent_requests"
    __table_args__ = (
        UniqueConstraint("owner_id", "session_id", "idempotency_key_hash", name="uq_agent_requests_owner_session_idempotency"),
        Index("ix_agent_requests_owner_session_status", "owner_id", "session_id", "status"),
        Index("ix_agent_requests_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("owner_sessions.id", ondelete="CASCADE"), nullable=False)
    connection_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_transcript_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    idempotency_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    route_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_identifier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConversationTurnModel(TimestampedModel, Base):
    """Internal text-only conversation turn; raw audio is never stored."""

    __tablename__ = "conversation_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_conversation_turns_conversation_sequence"),
        Index("ix_conversation_turns_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[ConversationTurnRole] = mapped_column(
        _enum_type(ConversationTurnRole, "conversation_turn_role"),
        nullable=False,
    )
    status: Mapped[ConversationTurnStatus] = mapped_column(
        _enum_type(ConversationTurnStatus, "conversation_turn_status"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_requests.id", ondelete="SET NULL"), nullable=True)
    safe_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class StructuredMemoryModel(TimestampedModel, Base):
    """Authoritative structured memory; semantic indexing is intentionally absent in M2."""

    __tablename__ = "structured_memories"
    __table_args__ = (
        Index(
            "ix_structured_memories_retention_cleanup",
            "retention_category",
            "pinned",
            "expires_at",
        ),
        Index("ix_structured_memories_category_created", "category", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    category: Mapped[MemoryCategory] = mapped_column(
        _enum_type(MemoryCategory, "memory_category"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[MemorySource] = mapped_column(
        _enum_type(MemorySource, "memory_source"),
        nullable=False,
    )
    source_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    retention_category: Mapped[RetentionCategory] = mapped_column(
        _enum_type(RetentionCategory, "retention_category"),
        nullable=False,
    )
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PermissionSettingModel(TimestampedModel, Base):
    """Independently revocable capability setting without authentication credentials."""

    __tablename__ = "permission_settings"
    __table_args__ = (UniqueConstraint("capability", name="uq_permission_settings_capability"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    grant_state: Mapped[PermissionGrantState] = mapped_column(
        _enum_type(PermissionGrantState, "permission_grant_state"),
        default=PermissionGrantState.DISABLED,
        nullable=False,
    )
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class PendingConfirmationModel(TimestampedModel, Base):
    """One-time confirmation challenge state; action execution remains a later milestone."""

    __tablename__ = "pending_confirmations"
    __table_args__ = (
        Index("ix_pending_confirmations_status_expires", "status", "expires_at"),
        Index("ix_pending_confirmations_owner_session_status_expires", "owner_id", "owner_session_id", "status", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    permission_setting_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("permission_settings.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("owners.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_session_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("owner_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ConfirmationStatus] = mapped_column(
        _enum_type(ConfirmationStatus, "confirmation_status"),
        default=ConfirmationStatus.AWAITING_CONFIRMATION,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ConfirmationConsumptionModel(Base):
    """Immutable audit/consumption row for a confirmation challenge."""

    __tablename__ = "confirmation_consumptions"
    __table_args__ = (UniqueConstraint("confirmation_id", name="uq_confirmation_consumptions_confirmation"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    confirmation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pending_confirmations.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[ConfirmationDecision] = mapped_column(
        _enum_type(ConfirmationDecision, "confirmation_decision"),
        nullable=False,
    )
    consumed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEventModel(Base):
    """Content-minimized audit event without tokens or secret payloads."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_occurred", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    actor_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    subject_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    safe_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class SchedulerJobMetadataModel(TimestampedModel, Base):
    """Metadata-only placeholder for future APScheduler job persistence."""

    __tablename__ = "scheduler_job_metadata"
    __table_args__ = (
        UniqueConstraint("job_key", name="uq_scheduler_job_metadata_job_key"),
        Index("ix_scheduler_job_metadata_next_run", "enabled", "next_run_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_key: Mapped[str] = mapped_column(String(128), nullable=False)
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_status: Mapped[SchedulerJobStatus | None] = mapped_column(
        _enum_type(SchedulerJobStatus, "scheduler_job_status"),
        nullable=True,
    )
    safe_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class SafeServiceConfigurationModel(TimestampedModel, Base):
    """Persist non-secret service configuration metadata only."""

    __tablename__ = "safe_service_configurations"
    __table_args__ = (UniqueConstraint("config_key", name="uq_safe_service_configurations_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class OwnerModel(TimestampedModel, Base):
    """The one v1 owner; the unique slot prevents concurrent second bootstrap rows."""

    __tablename__ = "owners"
    __table_args__ = (
        UniqueConstraint("owner_slot", name="uq_owners_singleton_slot"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_slot: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)


class OwnerSessionModel(Base):
    """Server-managed opaque-session metadata; raw bearer tokens are never persisted."""

    __tablename__ = "owner_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_owner_sessions_token_hash"),
        Index("ix_owner_sessions_owner_active", "owner_id", "revoked_at", "expires_at"),
        Index("ix_owner_sessions_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    client_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
