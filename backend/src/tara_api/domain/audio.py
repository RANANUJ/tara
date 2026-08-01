"""Framework-independent M7 audio and VAD contracts."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class AudioSessionState(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    LISTENING = "listening"
    SPEECH_DETECTED = "speech_detected"
    END_OF_TURN_PENDING = "end_of_turn_pending"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class AudioFormatError(ValueError):
    """Raised when an audio format is outside the M7 PCM contract."""


@dataclass(frozen=True, slots=True)
class AudioFormat:
    sample_rate: int = 16000
    sample_width_bytes: int = 2
    channels: int = 1
    frame_ms: int = 20
    endianness: str = "little"

    def validate(self) -> None:
        if self.sample_rate != 16000:
            raise AudioFormatError("unsupported sample rate")
        if self.sample_width_bytes != 2:
            raise AudioFormatError("unsupported sample width")
        if self.channels != 1:
            raise AudioFormatError("stereo audio is not supported")
        if self.frame_ms != 20:
            raise AudioFormatError("unsupported frame duration")
        if self.endianness != "little":
            raise AudioFormatError("unsupported endianness")

    @property
    def frame_bytes(self) -> int:
        return self.sample_rate * self.sample_width_bytes * self.channels * self.frame_ms // 1000

    @property
    def frame_samples(self) -> int:
        return self.sample_rate * self.frame_ms // 1000


@dataclass(frozen=True, slots=True)
class AudioFrame:
    audio_session_id: UUID
    sequence: int
    payload: bytes


class VoiceActivityDetector(Protocol):
    def speech_probability(self, frame: AudioFrame, audio_format: AudioFormat) -> float: ...
