"""Pure domain values used by safety, tools, and future application services."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | tuple[JsonValue, ...] | dict[str, JsonValue]


def _freeze_json(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, dict):
        return {key: _freeze_json(item) for key, item in value.items()}
    return value


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class ConversationId:
    """Opaque conversation identifier with no persistence dependency."""

    value: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class TurnId:
    """Opaque conversation-turn identifier with no persistence dependency."""

    value: UUID = field(default_factory=uuid4)


class AssistantState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SPEAKING = "speaking"
    OFFLINE = "offline"
    ERROR = "error"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ActionRiskLevel(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_REVERSIBLE = "local_reversible"
    OUTWARD_FACING = "outward_facing"
    DESTRUCTIVE = "destructive"
    FINANCIAL = "financial"
    CALL = "call"


class ConfirmationStatus(StrEnum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REJECTED = "rejected"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    APPROVED = "approved"
    EXECUTING = "executing"


class RetentionCategory(StrEnum):
    PREFERENCE = "preference"
    TASK = "task"
    CASUAL = "casual"


class ToolResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    INVALID = "invalid"
    UNKNOWN_TOOL = "unknown_tool"
    CONFIRMATION_REQUIRED = "confirmation_required"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    id: TurnId
    conversation_id: ConversationId
    sequence: int
    role: MessageRole
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IntentClassificationResult:
    intent: str
    confidence: float
    requires_clarification: bool
    rationale_code: str


@dataclass(frozen=True, slots=True)
class PermissionScope:
    capability: str
    targets: tuple[str, ...] = ()

    def allows(self, target: str | None = None) -> bool:
        return target is None or not self.targets or target in self.targets


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    permission_scope: PermissionScope
    risk_level: ActionRiskLevel
    summary_template: str
    timeout_seconds: int = 30
    idempotent: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.version or not self.summary_template:
            raise ValueError("tool name, version, and summary template are required")
        if self.timeout_seconds < 1:
            raise ValueError("tool timeout must be positive")


@dataclass(frozen=True, slots=True)
class ToolRequest:
    tool_name: str
    schema_version: str
    arguments: dict[str, JsonValue]
    conversation_id: ConversationId | None = None
    turn_id: TurnId | None = None
    request_id: UUID = field(default_factory=uuid4)
    idempotency_key_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_name or not self.schema_version:
            raise ValueError("tool name and schema version are required")
        object.__setattr__(self, "arguments", _freeze_json(self.arguments))

    def canonical_hash(self) -> str:
        """Hash every executable field, excluding transport-only request identity."""
        payload: JsonValue = {
            "tool_name": self.tool_name,
            "schema_version": self.schema_version,
            "arguments": self.arguments,
            "idempotency_key_hash": self.idempotency_key_hash,
        }
        return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolResult:
    status: ToolResultStatus
    safe_summary: str
    data: dict[str, JsonValue] = field(default_factory=dict)
    confirmation: PendingConfirmation | None = None


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    id: UUID
    request_hash: str
    tool_name: str
    prompt: str
    status: ConfirmationStatus
    expires_at: datetime
    created_at: datetime
    owner_id: UUID | None = None
    session_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ConfirmationAuthorization:
    confirmation_id: UUID
    request_hash: str
    expires_at: datetime
    owner_id: UUID | None = None
    session_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ConfirmationResponse:
    status: ConfirmationStatus
    authorization: ConfirmationAuthorization | None = None


@dataclass(frozen=True, slots=True)
class StructuredMemory:
    id: UUID
    category: str
    content: str
    retention_category: RetentionCategory
    pinned: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: str
    outcome: str
    occurred_at: datetime
    subject_reference: str | None = None
    safe_metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LatencyTrace:
    trace_id: UUID
    operation: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
