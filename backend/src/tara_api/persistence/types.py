"""Persistence enums, timestamps, and non-ORM record types."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize an aware timestamp to UTC and reject naive input."""
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware UTC values")
    return value.astimezone(UTC)


class ConversationTurnRole(StrEnum):
    """Persisted speaker roles supported by the current conversation model."""

    USER = "user"
    ASSISTANT = "assistant"


class ConversationTurnStatus(StrEnum):
    """Turn lifecycle states from the assistant protocol."""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MemoryCategory(StrEnum):
    """Structured-memory categories defined by the API contract."""

    PREFERENCE = "preference"
    FACT = "fact"
    TASK = "task"
    CONVERSATION_SUMMARY = "conversation_summary"


class MemorySource(StrEnum):
    """Safe provenance sources for structured memory."""

    USER = "user"
    CONVERSATION = "conversation"
    CONSOLIDATION = "consolidation"
    IMPORT = "import"


class RetentionCategory(StrEnum):
    """Retention classes from the PRD memory policy."""

    PREFERENCE = "preference"
    TASK = "task"
    CASUAL = "casual"


class MemoryIndexOperation(StrEnum):
    """Idempotent semantic-index work derived from authoritative SQLite memory."""

    UPSERT = "upsert"
    DELETE = "delete"


class MemoryTaskStatus(StrEnum):
    """Explicit state for task-category memories; non-task memories omit it."""

    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PermissionGrantState(StrEnum):
    """Default-deny capability grant states."""

    ENABLED = "enabled"
    DISABLED = "disabled"


class ConfirmationStatus(StrEnum):
    """Server-owned confirmation state machine values."""

    PROPOSED = "proposed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REJECTED_BY_POLICY = "rejected_by_policy"
    REJECTED = "rejected"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ConfirmationDecision(StrEnum):
    """Immutable consumption decisions for a confirmation challenge."""

    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SchedulerJobStatus(StrEnum):
    """Metadata-only scheduler states for a later scheduling milestone."""

    SCHEDULED = "scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: UUID
    label: str | None
    created_at: datetime
    updated_at: datetime
    owner_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ConversationTurnRecord:
    id: UUID
    conversation_id: UUID
    sequence: int
    role: ConversationTurnRole
    status: ConversationTurnStatus
    content: str
    created_at: datetime
    updated_at: datetime
    agent_request_id: UUID | None = None
    safe_metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class AgentRequestRecord:
    id: UUID
    owner_id: UUID
    session_id: UUID
    connection_id: UUID | None
    conversation_id: UUID
    source: str
    source_transcript_id: UUID | None
    idempotency_key_hash: str
    status: str
    route_category: str | None
    failure_code: str | None
    provider_name: str | None
    model_identifier: str | None
    usage: dict[str, int] | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StructuredMemoryRecord:
    id: UUID
    category: MemoryCategory
    content: str
    source: MemorySource
    source_reference: str | None
    retention_category: RetentionCategory
    pinned: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    task_status: MemoryTaskStatus | None = None

    def to_export_dict(self) -> dict[str, str | bool | None]:
        """Return a JSON-serializable export representation without internal ORM state."""
        return {
            "id": str(self.id),
            "category": self.category.value,
            "content": self.content,
            "source": self.source.value,
            "source_reference": self.source_reference,
            "retention_category": self.retention_category.value,
            "pinned": self.pinned,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "task_status": self.task_status.value if self.task_status else None,
        }


@dataclass(frozen=True, slots=True)
class MemoryIndexOutboxRecord:
    id: UUID
    memory_id: UUID
    operation: MemoryIndexOperation
    created_at: datetime
    processed_at: datetime | None
    attempts: int


@dataclass(frozen=True, slots=True)
class PermissionSettingRecord:
    id: UUID
    capability: str
    grant_state: PermissionGrantState
    scope: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PendingConfirmationRecord:
    id: UUID
    conversation_id: UUID | None
    permission_setting_id: UUID | None
    owner_id: UUID | None
    owner_session_id: UUID | None
    action_type: str
    action_summary: str
    action_hash: str
    status: ConfirmationStatus
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ConfirmationConsumptionRecord:
    id: UUID
    confirmation_id: UUID
    decision: ConfirmationDecision
    consumed_at: datetime
    idempotency_key_hash: str | None
    audit_summary: str | None


@dataclass(frozen=True, slots=True)
class AuditEventRecord:
    id: UUID
    event_type: str
    outcome: str
    occurred_at: datetime
    actor_reference: str | None
    subject_reference: str | None
    safe_metadata: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class SchedulerJobMetadataRecord:
    id: UUID
    job_key: str
    job_type: str
    enabled: bool
    timezone: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: SchedulerJobStatus | None
    safe_metadata: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SafeServiceConfigurationRecord:
    id: UUID
    config_key: str
    value: dict[str, object]
    created_at: datetime
    updated_at: datetime


class ConfirmationAlreadyConsumedError(RuntimeError):
    """Raised when a confirmation has already been consumed or is not pending."""


class ConfirmationExpiredError(RuntimeError):
    """Raised when a confirmation is no longer eligible for consumption."""


class UnsafeConfigurationKeyError(ValueError):
    """Raised when a configuration key could identify a secret value."""
