"""Framework-independent contracts for Tara's local text-model boundary."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

MAX_AGENT_INPUT_CHARS = 12_000
MAX_MODEL_OUTPUT_CHARS = 8_000


class AgentState(StrEnum):
    QUEUED = "queued"
    ROUTING = "routing"
    RETRIEVING_CONTEXT = "retrieving_context"
    GENERATING = "generating"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    COMPLETED = "completed"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class AgentInputSource(StrEnum):
    DIRECT_TEXT = "direct_text"
    FINAL_TRANSCRIPT = "final_transcript"


class AgentError(StrEnum):
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    REQUEST_TOO_LARGE = "request_too_large"
    CONTEXT_LIMIT_EXCEEDED = "context_limit_exceeded"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    RESPONSE_TOO_LARGE = "response_too_large"
    REQUEST_CANCELED = "request_canceled"
    MODEL_NOT_AVAILABLE = "model_not_available"
    INTERNAL_MODEL_ERROR = "internal_model_error"


class IntentCategory(StrEnum):
    CONVERSATION = "conversation"
    FACTUAL_QUESTION = "factual_question"
    MEMORY_QUERY = "memory_query"
    SAFE_READ_ONLY_REQUEST = "safe_read_only_request"
    CONSEQUENTIAL_ACTION_REQUEST = "consequential_action_request"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class ModelRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ModelFinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


class AgentRequestStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELED = "canceled"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderHealthState(StrEnum):
    DISABLED = "disabled"
    CONFIGURED = "configured"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC")


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: ModelRole
    text: str

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_AGENT_INPUT_CHARS:
            raise ValueError("invalid model message")


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if any(value is not None and value < 0 for value in (self.input_tokens, self.output_tokens)):
            raise ValueError("model usage cannot be negative")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    request_id: UUID
    messages: tuple[ModelMessage, ...]
    context_token_budget: int
    output_token_budget: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.messages or self.context_token_budget < 1 or self.output_token_budget < 1:
            raise ValueError("invalid model request")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str
    model_identifier: str
    finish_reason: ModelFinishReason
    duration_ms: int
    usage: ModelUsage | None = None

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_MODEL_OUTPUT_CHARS or not self.model_identifier or self.duration_ms < 0:
            raise ValueError("invalid model response")


@dataclass(frozen=True, slots=True)
class IntentClassification:
    category: IntentCategory
    confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("intent confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class AgentSession:
    agent_session_id: UUID
    owner_id: UUID
    session_id: UUID
    connection_id: UUID | None
    created_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class AgentRequest:
    request_id: UUID
    agent_session_id: UUID
    owner_id: UUID
    session_id: UUID
    connection_id: UUID | None
    source: AgentInputSource
    text: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_AGENT_INPUT_CHARS:
            raise ValueError("invalid agent request")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class AgentResponse:
    request_id: UUID
    text: str
    state: AgentState
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_MODEL_OUTPUT_CHARS:
            raise ValueError("invalid agent response")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class AgentTurn:
    turn_id: UUID
    request: AgentRequest
    response: AgentResponse | None
    state: AgentState
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")


@dataclass(frozen=True, slots=True)
class AgentTrace:
    request_id: UUID
    state: AgentState
    started_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_utc(self.started_at, "started_at")
        if self.completed_at is not None:
            _require_utc(self.completed_at, "completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot precede started_at")


@dataclass(frozen=True, slots=True)
class ModelReadiness:
    ready: bool
    state: ProviderHealthState
    diagnostic_code: AgentError | None = None


@dataclass(frozen=True, slots=True)
class LanguageModelHealthSnapshot:
    configured: bool
    required: bool
    provider: str
    model: str | None
    state: ProviderHealthState
    ready: bool
    streaming_supported: bool
    checked_at: datetime
    latency_ms: int
    diagnostic_code: AgentError | None = None

    def __post_init__(self) -> None:
        _require_utc(self.checked_at, "checked_at")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")


class LanguageModelProvider(Protocol):
    name: str
    model_identifier: str
    streaming_supported: bool

    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    async def readiness(self) -> ModelReadiness: ...


class LanguageModelHealthProvider(Protocol):
    async def snapshot(self) -> LanguageModelHealthSnapshot: ...


class ModelRequestValidator(Protocol):
    def validate(self, request: ModelRequest) -> None: ...


class ModelResponseValidator(Protocol):
    def validate(self, response: ModelResponse) -> ModelResponse: ...


class ModelClock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class ModelProviderFailure(Exception):
    code: AgentError
    message: str = field(default="Language model request failed.")

    def __str__(self) -> str:
        return self.message
