"""Framework-independent M11A foreground wake-word contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

MAX_WAKE_PHRASE_LENGTH = 64


class WakeWordState(StrEnum):
    DISABLED = "disabled"
    IDLE = "idle"
    LISTENING = "listening"
    DETECTING = "detecting"
    TRIGGERED = "triggered"
    COOLDOWN = "cooldown"
    CANCELED = "canceled"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class WakeWordError(StrEnum):
    WAKEWORD_DISABLED = "wakeword_disabled"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_AUDIO_FRAME = "invalid_audio_frame"
    UNSUPPORTED_AUDIO_FORMAT = "unsupported_audio_format"
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
    STALE_AUDIO_SESSION = "stale_audio_session"
    CONNECTION_MISMATCH = "connection_mismatch"
    SESSION_INVALIDATED = "session_invalidated"
    COOLDOWN_ACTIVE = "cooldown_active"
    REQUEST_CANCELED = "request_canceled"
    DETECTOR_TIMEOUT = "detector_timeout"
    INVALID_DETECTOR_RESPONSE = "invalid_detector_response"
    FOREGROUND_REQUIRED = "foreground_required"
    MICROPHONE_NOT_ACTIVE = "microphone_not_active"
    INTERNAL_WAKEWORD_ERROR = "internal_wakeword_error"


class WakeWordCapability(StrEnum):
    FOREGROUND_WEB = "foreground_web"
    NATIVE_BACKGROUND = "native_background"
    SCREEN_OFF = "screen_off"
    LOCKED_DEVICE = "locked_device"
    OFFLINE = "offline"
    STREAMING_AUDIO = "streaming_audio"
    CONTINUOUS_LISTENING = "continuous_listening"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC")


def normalize_wake_phrase(value: str) -> str:
    """Normalize a configured phrase without retaining or transcribing audio."""
    normalized = " ".join(value.casefold().split())
    if not normalized or len(normalized) > MAX_WAKE_PHRASE_LENGTH:
        raise ValueError("invalid wake phrase")
    return normalized


@dataclass(frozen=True, slots=True)
class WakeWordConfidence:
    value: float

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 1:
            raise ValueError("wake-word confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class WakeWordSessionIdentity:
    owner_id: UUID
    session_id: UUID
    connection_id: UUID
    audio_session_id: UUID


@dataclass(frozen=True, slots=True)
class WakeWordAudioFrame:
    sequence: int
    pcm16: bytes
    sample_rate: int
    sample_width_bytes: int
    channels: int
    duration_ms: int
    captured_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.sample_rate <= 0 or self.sample_width_bytes <= 0 or self.channels <= 0 or self.duration_ms <= 0:
            raise ValueError("invalid wake-word audio frame metadata")
        expected_bytes = self.sample_rate * self.sample_width_bytes * self.channels * self.duration_ms // 1000
        if expected_bytes <= 0 or len(self.pcm16) != expected_bytes:
            raise ValueError("invalid wake-word audio frame")
        _require_utc(self.captured_at, "captured_at")


@dataclass(frozen=True, slots=True)
class WakeWordDetectionRequest:
    identity: WakeWordSessionIdentity
    frame: WakeWordAudioFrame
    phrase: str
    language_mode: str
    requested_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "phrase", normalize_wake_phrase(self.phrase))
        if self.language_mode not in {"auto", "en", "hi", "mixed"}:
            raise ValueError("invalid wake-word language mode")
        _require_utc(self.requested_at, "requested_at")


@dataclass(frozen=True, slots=True)
class WakeWordDetectionResult:
    detected: bool
    confidence: WakeWordConfidence | None
    provider: str
    completed_at: datetime

    def __post_init__(self) -> None:
        if not self.provider or len(self.provider) > 64:
            raise ValueError("invalid wake-word provider")
        if self.detected and self.confidence is None:
            raise ValueError("wake-word detections require confidence")
        _require_utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class WakeWordEvent:
    event_id: UUID
    identity: WakeWordSessionIdentity
    confidence: WakeWordConfidence
    occurred_at: datetime
    state: WakeWordState = WakeWordState.TRIGGERED

    def __post_init__(self) -> None:
        if self.state is not WakeWordState.TRIGGERED:
            raise ValueError("wake-word event must be triggered")
        _require_utc(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class WakeWordConfiguration:
    provider: str
    phrase: str
    enabled: bool
    confidence_threshold: float
    minimum_consecutive_detections: int
    cooldown_seconds: float
    debounce_seconds: float
    frame_duration_ms: int
    maximum_buffered_frames: int
    language_mode: str
    foreground_only: bool = True
    maximum_frame_age_seconds: float = 2
    suspend_during_tts: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "phrase", normalize_wake_phrase(self.phrase))
        if not self.provider or len(self.provider) > 64:
            raise ValueError("invalid wake-word provider")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("invalid wake-word confidence threshold")
        if self.minimum_consecutive_detections <= 0 or self.cooldown_seconds < 0 or self.debounce_seconds < 0:
            raise ValueError("invalid wake-word debounce or cooldown")
        if self.frame_duration_ms <= 0 or self.maximum_buffered_frames <= 0 or self.maximum_frame_age_seconds <= 0:
            raise ValueError("invalid wake-word frame limits")
        if self.language_mode not in {"auto", "en", "hi", "mixed"}:
            raise ValueError("invalid wake-word language mode")
        if not self.foreground_only:
            raise ValueError("wake-word detection must remain foreground-only")


@dataclass(frozen=True, slots=True)
class WakeWordProviderHealth:
    configured: bool
    enabled: bool
    provider: str
    state: WakeWordState
    ready: bool
    phrase_configured: bool
    foreground_only: bool
    offline_capable: bool
    streaming_audio_supported: bool
    continuous_while_page_open: bool
    native_background_supported: bool
    screen_off_supported: bool
    locked_device_supported: bool
    checked_at: datetime
    latency_ms: int
    diagnostic_code: WakeWordError | None = None

    def __post_init__(self) -> None:
        if self.latency_ms < 0:
            raise ValueError("wake-word health latency cannot be negative")
        if self.native_background_supported or self.screen_off_supported or self.locked_device_supported:
            raise ValueError("M11A does not support native or screen-off wake word")
        _require_utc(self.checked_at, "checked_at")


class WakeWordFailure(RuntimeError):
    """Stable code and generic message for wake-word boundary failures."""

    def __init__(self, code: WakeWordError) -> None:
        super().__init__("Wake-word detection could not be completed.")
        self.code = code


class WakeWordDetector(Protocol):
    name: str
    offline_capable: bool

    async def detect(self, request: WakeWordDetectionRequest) -> WakeWordDetectionResult: ...

    async def readiness(self) -> bool: ...


class WakeWordHealthProvider(Protocol):
    async def snapshot(self) -> WakeWordProviderHealth: ...


class WakeWordSessionValidator(Protocol):
    async def is_owner_session_active(self, owner_id: UUID, session_id: UUID) -> bool: ...


class WakeWordClock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...
