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


class IntentReasonCode(StrEnum):
    """Stable, non-LLM rationale codes for deterministic intent routing."""

    INFORMATIONAL_ACTION = "informational_action"
    MEMORY_REFERENCE = "memory_reference"
    READ_ONLY_VERB = "read_only_verb"
    CONSEQUENTIAL_MESSAGE = "consequential_message"
    CONSEQUENTIAL_CALL = "consequential_call"
    CONSEQUENTIAL_DESTRUCTIVE = "consequential_destructive"
    CONSEQUENTIAL_FINANCIAL = "consequential_financial"
    CONSEQUENTIAL_EXTERNAL_WRITE = "consequential_external_write"
    CONSEQUENTIAL_ACCOUNT_SECURITY = "consequential_account_security"
    QUESTION = "question"
    CONVERSATIONAL = "conversational"
    LOW_CONFIDENCE = "low_confidence"
    UNSUPPORTED = "unsupported"


class ContextSensitivity(StrEnum):
    """Server-controlled context sensitivity labels."""

    NORMAL = "normal"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class ContextSourceKind(StrEnum):
    """Safe persisted sources permitted in M9B model context."""

    STRUCTURED_MEMORY = "structured_memory"
    CONVERSATION_TURN = "conversation_turn"


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
class IntentRoute:
    """Deterministic routing output; it never authorizes an action."""

    category: IntentCategory
    confidence: float
    reason_code: IntentReasonCode
    clarification: str | None = None
    consequential_risk: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("intent confidence must be between zero and one")
        if self.consequential_risk != (self.category == IntentCategory.CONSEQUENTIAL_ACTION_REQUEST):
            raise ValueError("consequential risk must match the intent category")
        if self.clarification is not None and not self.clarification.strip():
            raise ValueError("clarification cannot be blank")


@dataclass(frozen=True, slots=True)
class ContextSourceMetadata:
    """Non-secret provenance retained with a selected context item."""

    kind: ContextSourceKind
    record_id: UUID
    category: str | None = None
    pinned: bool = False
    role: ModelRole | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("context sequence cannot be negative")
        if self.kind == ContextSourceKind.STRUCTURED_MEMORY and self.role is not None:
            raise ValueError("memory context cannot have a message role")
        if self.kind == ContextSourceKind.CONVERSATION_TURN and self.role is None:
            raise ValueError("conversation context requires a message role")


@dataclass(frozen=True, slots=True)
class ContextItem:
    """Bounded untrusted content selected for a future prompt."""

    text: str
    sensitivity: ContextSensitivity
    source: ContextSourceMetadata
    truncated: bool = False

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_AGENT_INPUT_CHARS:
            raise ValueError("invalid context item")
        if self.sensitivity == ContextSensitivity.RESTRICTED:
            raise ValueError("restricted context cannot be represented for prompting")


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Deterministic record, character, and estimated-token limits."""

    memory_limit: int
    recent_turn_limit: int
    memory_item_char_limit: int
    recent_turn_char_limit: int
    total_char_limit: int
    estimated_token_limit: int

    def __post_init__(self) -> None:
        values = (
            self.memory_limit,
            self.recent_turn_limit,
            self.memory_item_char_limit,
            self.recent_turn_char_limit,
            self.total_char_limit,
            self.estimated_token_limit,
        )
        if any(value < 1 for value in values):
            raise ValueError("context budgets must be positive")
        if self.memory_item_char_limit > self.total_char_limit or self.recent_turn_char_limit > self.total_char_limit:
            raise ValueError("context item limits cannot exceed the total limit")
        if self.total_char_limit > self.estimated_token_limit * 4:
            raise ValueError("context character limit exceeds the estimated token limit")


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Server-created request for one authenticated owner's persisted context."""

    owner_id: UUID
    conversation_id: UUID | None


@dataclass(frozen=True, slots=True)
class StructuredContext:
    """Safe, ordered context selected without semantic retrieval."""

    items: tuple[ContextItem, ...]
    estimated_tokens: int
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.estimated_tokens < 0:
            raise ValueError("estimated tokens cannot be negative")


@dataclass(frozen=True, slots=True)
class PromptBuildResult:
    """Structured provider-neutral messages with bounded untrusted context."""

    messages: tuple[ModelMessage, ...]
    estimated_tokens: int
    context_items_included: int
    context_truncated: bool

    def __post_init__(self) -> None:
        if not self.messages or self.estimated_tokens < 1 or self.context_items_included < 0:
            raise ValueError("invalid prompt build result")


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


class IntentRouter(Protocol):
    def classify(self, text: str) -> IntentRoute: ...


class StructuredContextProvider(Protocol):
    async def get_context(self, request: ContextRequest) -> StructuredContext: ...


class PromptBuilder(Protocol):
    def build(
        self,
        user_text: str,
        context: StructuredContext,
        *,
        model_context_token_budget: int,
    ) -> PromptBuildResult: ...


@dataclass(frozen=True, slots=True)
class ModelProviderFailure(Exception):
    code: AgentError
    message: str = field(default="Language model request failed.")

    def __str__(self) -> str:
        return self.message
