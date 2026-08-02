"""Framework-independent M10A text-to-speech contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

MAX_SYNTHESIS_TEXT_CHARS = 4_000
MAX_SYNTHESIS_AUDIO_BYTES = 8 * 1024 * 1024
MAX_SPEECH_CHUNK_BYTES = 64 * 1024
SUPPORTED_SAMPLE_RATES = frozenset({16_000, 22_050, 24_000})


class SpeechEncoding(StrEnum):
    PCM_S16LE = "pcm_s16le"


class SpeechContainer(StrEnum):
    RAW = "raw"
    WAV = "wav"


class SpeechLanguage(StrEnum):
    ENGLISH = "en"
    HINDI = "hi"
    MIXED = "mixed"


class SpeechSynthesisState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    SYNTHESIZING = "synthesizing"
    CHUNKING = "chunking"
    COMPLETED = "completed"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class SpeechSynthesisError(StrEnum):
    EMPTY_TEXT = "empty_text"
    TEXT_TOO_LONG = "text_too_long"
    INVALID_TEXT = "invalid_text"
    INVALID_AGENT_SOURCE = "invalid_agent_source"
    SOURCE_NOT_COMPLETED = "source_not_completed"
    DUPLICATE_REQUEST = "duplicate_request"
    QUEUE_FULL = "queue_full"
    CONNECTION_REQUEST_LIMIT = "connection_request_limit"
    SESSION_REQUEST_LIMIT = "session_request_limit"
    OWNER_REQUEST_LIMIT = "owner_request_limit"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    REQUEST_CANCELED = "request_canceled"
    VOICE_NOT_AVAILABLE = "voice_not_available"
    LANGUAGE_NOT_SUPPORTED = "language_not_supported"
    FORMAT_NOT_SUPPORTED = "format_not_supported"
    INVALID_AUDIO_RESPONSE = "invalid_audio_response"
    AUDIO_TOO_LARGE = "audio_too_large"
    RETAINED_AUDIO_LIMIT = "retained_audio_limit"
    INVALID_AUDIO_METADATA = "invalid_audio_metadata"
    REQUEST_TIMED_OUT = "request_timed_out"
    SESSION_INVALIDATED = "session_invalidated"
    PERSISTENCE_FAILURE = "persistence_failure"
    SYNTHESIS_FAILED = "synthesis_failed"
    INTERNAL_TTS_ERROR = "internal_tts_error"


class SpeechProviderState(StrEnum):
    DISABLED = "disabled"
    CONFIGURED = "configured"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC")


@dataclass(frozen=True, slots=True)
class SpeechVoice:
    identifier: str

    def __post_init__(self) -> None:
        if not self.identifier or len(self.identifier) > 128 or any(character.isspace() for character in self.identifier):
            raise ValueError("invalid speech voice")


@dataclass(frozen=True, slots=True)
class SpeechFormat:
    encoding: SpeechEncoding = SpeechEncoding.PCM_S16LE
    sample_rate: int = 22_050
    channels: int = 1
    bit_depth: int = 16
    container: SpeechContainer = SpeechContainer.RAW

    def __post_init__(self) -> None:
        if self.sample_rate not in SUPPORTED_SAMPLE_RATES or self.channels != 1 or self.bit_depth != 16:
            raise ValueError("unsupported speech format")
        if self.encoding is not SpeechEncoding.PCM_S16LE:
            raise ValueError("unsupported speech encoding")

    @property
    def bytes_per_sample(self) -> int:
        return self.bit_depth // 8

    @property
    def bytes_per_frame(self) -> int:
        return self.bytes_per_sample * self.channels


@dataclass(frozen=True, slots=True)
class SpeechSynthesisRequest:
    synthesis_id: UUID
    owner_id: UUID
    session_id: UUID
    text: str
    voice: SpeechVoice
    language: SpeechLanguage
    output_format: SpeechFormat
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.text or len(self.text) > MAX_SYNTHESIS_TEXT_CHARS:
            raise ValueError("invalid synthesis text")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class SpeechAudioChunk:
    sequence: int
    audio: bytes
    is_final: bool = False
    byte_offset: int = 0
    byte_length: int | None = None
    start_duration_ms: int | None = None
    end_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0 or not self.audio or len(self.audio) > MAX_SPEECH_CHUNK_BYTES:
            raise ValueError("invalid speech audio chunk")
        if self.byte_offset < 0 or (self.byte_length is not None and self.byte_length != len(self.audio)):
            raise ValueError("invalid speech chunk byte metadata")
        if self.start_duration_ms is not None and self.start_duration_ms < 0:
            raise ValueError("invalid speech chunk start duration")
        if self.end_duration_ms is not None and (
            self.end_duration_ms < 0
            or self.start_duration_ms is None
            or self.end_duration_ms < self.start_duration_ms
        ):
            raise ValueError("invalid speech chunk end duration")


@dataclass(frozen=True, slots=True)
class SpeechUsageMetadata:
    input_characters: int
    audio_bytes: int

    def __post_init__(self) -> None:
        if self.input_characters < 0 or self.audio_bytes < 0:
            raise ValueError("speech usage cannot be negative")


@dataclass(frozen=True, slots=True)
class SpeechTimingMetadata:
    synthesis_duration_ms: int
    audio_duration_ms: int

    def __post_init__(self) -> None:
        if self.synthesis_duration_ms < 0 or self.audio_duration_ms < 0:
            raise ValueError("speech timing cannot be negative")


@dataclass(frozen=True, slots=True)
class SpeechSynthesisResult:
    synthesis_id: UUID
    audio: bytes
    output_format: SpeechFormat
    sample_count: int
    timing: SpeechTimingMetadata
    usage: SpeechUsageMetadata
    completed_at: datetime
    chunks: tuple[SpeechAudioChunk, ...] = ()

    def __post_init__(self) -> None:
        if not self.audio or len(self.audio) > MAX_SYNTHESIS_AUDIO_BYTES or self.sample_count < 0:
            raise ValueError("invalid synthesized audio")
        if len(self.audio) % self.output_format.bytes_per_frame:
            raise ValueError("misaligned synthesized audio")
        if self.sample_count != len(self.audio) // self.output_format.bytes_per_frame:
            raise ValueError("inconsistent synthesized audio metadata")
        expected_duration = round(self.sample_count * 1000 / self.output_format.sample_rate)
        if self.timing.audio_duration_ms != expected_duration:
            raise ValueError("inconsistent synthesized audio duration")
        if self.usage.audio_bytes != len(self.audio):
            raise ValueError("inconsistent speech usage")
        if self.chunks:
            if tuple(chunk.sequence for chunk in self.chunks) != tuple(range(len(self.chunks))):
                raise ValueError("invalid speech chunk sequence")
            if self.chunks[-1].is_final is not True or b"".join(chunk.audio for chunk in self.chunks) != self.audio:
                raise ValueError("inconsistent speech chunks")
            if sum(chunk.is_final for chunk in self.chunks) != 1:
                raise ValueError("invalid speech final chunk")
        _require_utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class SpeechProviderReadiness:
    ready: bool
    state: SpeechProviderState
    diagnostic_code: SpeechSynthesisError | None = None


@dataclass(frozen=True, slots=True)
class SpeechProviderHealth:
    configured: bool
    required: bool
    provider: str
    state: SpeechProviderState
    ready: bool
    voice: str | None
    language_mode: str
    output_format: SpeechFormat | None
    streaming_supported: bool
    checked_at: datetime
    latency_ms: int
    diagnostic_code: SpeechSynthesisError | None = None

    def __post_init__(self) -> None:
        if self.latency_ms < 0:
            raise ValueError("speech health latency cannot be negative")
        _require_utc(self.checked_at, "checked_at")


class SpeechSynthesisFailure(RuntimeError):
    """Stable code and generic message for provider-boundary failures."""

    def __init__(self, code: SpeechSynthesisError) -> None:
        super().__init__("Speech synthesis could not be completed.")
        self.code = code


@dataclass(frozen=True, slots=True)
class ApprovedAgentResponse:
    """Server-resolved final response eligible for exactly one TTS identity."""

    agent_request_id: UUID
    owner_id: UUID
    session_id: UUID
    connection_id: UUID | None
    conversation_id: UUID
    text: str
    completed_at: datetime
    assistant_turn_id: UUID | None = None
    state: str = "completed"

    def __post_init__(self) -> None:
        if self.state != "completed" or not self.text:
            raise ValueError("agent response is not a completed final response")
        _require_utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class SynthesisCommand:
    """Client-safe command with no text or caller-controlled identity fields."""

    agent_request_id: UUID
    voice: SpeechVoice
    language: SpeechLanguage
    output_format: SpeechFormat
    assistant_turn_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SynthesisRequestIdentity:
    """Immutable, content-minimized identity retained by the process-local registry."""

    synthesis_request_id: UUID
    owner_id: UUID
    session_id: UUID
    connection_id: UUID | None
    conversation_id: UUID
    agent_request_id: UUID
    assistant_turn_id: UUID | None
    idempotency_key_hash: str
    provider: str
    voice: SpeechVoice
    language: SpeechLanguage
    output_format: SpeechFormat
    created_at: datetime

    def __post_init__(self) -> None:
        if len(self.idempotency_key_hash) != 64 or not self.provider:
            raise ValueError("invalid synthesis request identity")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class SynthesisRequestRecord:
    """Safe lifecycle metadata; it never contains synthesis text or audio bytes."""

    identity: SynthesisRequestIdentity
    state: SpeechSynthesisState
    updated_at: datetime
    error: SpeechSynthesisError | None = None
    audio_bytes: int = 0
    chunk_count: int = 0
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if self.audio_bytes < 0 or self.chunk_count < 0 or (self.duration_ms is not None and self.duration_ms < 0):
            raise ValueError("invalid synthesis request metadata")
        _require_utc(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class SynthesisServiceResult:
    """Service completion containing audio only while process-local retention permits it."""

    record: SynthesisRequestRecord
    result: SpeechSynthesisResult | None = None


class ApprovedAgentResponseSource(Protocol):
    """Server-side bridge that resolves M9-validated final responses by bound identity."""

    async def resolve_completed_response(
        self,
        *,
        owner_id: UUID,
        session_id: UUID,
        connection_id: UUID | None,
        agent_request_id: UUID,
        assistant_turn_id: UUID | None,
    ) -> ApprovedAgentResponse | None: ...


class SpeechSessionValidator(Protocol):
    async def is_owner_session_active(self, owner_id: UUID, session_id: UUID) -> bool: ...


class TextToSpeechProvider(Protocol):
    name: str
    voice: SpeechVoice
    streaming_supported: bool
    supported_formats: tuple[SpeechFormat, ...]
    supported_languages: tuple[SpeechLanguage, ...]

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult: ...

    async def readiness(self) -> SpeechProviderReadiness: ...


class TextToSpeechHealthProvider(Protocol):
    async def snapshot(self) -> SpeechProviderHealth: ...
