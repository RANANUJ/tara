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


@dataclass(frozen=True, slots=True)
class AudioFormat:
    sample_rate: int = 16000
    sample_width_bytes: int = 2
    channels: int = 1
    frame_ms: int = 20

    @property
    def frame_bytes(self) -> int:
        return self.sample_rate * self.sample_width_bytes * self.channels * self.frame_ms // 1000


@dataclass(frozen=True, slots=True)
class AudioFrame:
    audio_session_id: UUID
    sequence: int
    payload: bytes


class VoiceActivityDetector(Protocol):
    def speech_probability(self, frame: AudioFrame, audio_format: AudioFormat) -> float: ...
