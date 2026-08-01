"""Bounded PCM framing and deterministic M7 VAD state flow."""

import math
import struct
from dataclasses import dataclass
from uuid import UUID

from tara_api.domain.audio import AudioFormat, AudioFrame, AudioSessionState, VoiceActivityDetector

FRAME_MAGIC = b"TAR1"
FRAME_HEADER_BYTES = 24
CANONICAL_FORMAT = AudioFormat()


def decode_frame(data: bytes) -> AudioFrame:
    if len(data) < FRAME_HEADER_BYTES or data[:4] != FRAME_MAGIC:
        raise ValueError("invalid audio frame")
    session_id = UUID(bytes=data[4:20])
    sequence = struct.unpack("!I", data[20:24])[0]
    payload = data[24:]
    if len(payload) != CANONICAL_FORMAT.frame_bytes:
        raise ValueError("invalid audio payload length")
    return AudioFrame(session_id, sequence, payload)


def encode_frame(frame: AudioFrame) -> bytes:
    if len(frame.payload) != CANONICAL_FORMAT.frame_bytes:
        raise ValueError("invalid audio payload length")
    return FRAME_MAGIC + frame.audio_session_id.bytes + struct.pack("!I", frame.sequence) + frame.payload


class DeterministicVad:
    def __init__(self, threshold: float = 0.02) -> None:
        self._threshold = threshold

    def speech_probability(self, frame: AudioFrame, audio_format: AudioFormat) -> float:
        samples = struct.unpack(f"<{len(frame.payload) // 2}h", frame.payload)
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
        return min(1.0, max(0.0, rms / max(self._threshold, 0.0001)))


@dataclass(slots=True)
class AudioSession:
    session_id: UUID
    state: AudioSessionState = AudioSessionState.STARTING
    format_negotiated: bool = False
    last_sequence: int = -1
    speech_frames: int = 0
    silence_frames: int = 0

    def negotiate(self, audio_format: AudioFormat) -> None:
        if self.state != AudioSessionState.STARTING or audio_format != CANONICAL_FORMAT:
            raise ValueError("unsupported audio format")
        self.format_negotiated = True
        self.state = AudioSessionState.LISTENING

    def ingest(self, frame: AudioFrame, detector: VoiceActivityDetector) -> tuple[list[str], float]:
        if self.state not in {AudioSessionState.LISTENING, AudioSessionState.SPEECH_DETECTED, AudioSessionState.END_OF_TURN_PENDING} or not self.format_negotiated:
            raise ValueError("audio session is not accepting frames")
        if frame.audio_session_id != self.session_id or frame.sequence != self.last_sequence + 1:
            raise ValueError("audio frame sequence is invalid")
        self.last_sequence = frame.sequence
        probability = detector.speech_probability(frame, CANONICAL_FORMAT)
        events: list[str] = []
        if probability >= 1:
            self.speech_frames += 1
            self.silence_frames = 0
            if self.state == AudioSessionState.LISTENING and self.speech_frames >= 2:
                self.state = AudioSessionState.SPEECH_DETECTED
                events.append("vad.speech.started")
        elif self.state == AudioSessionState.SPEECH_DETECTED:
            self.silence_frames += 1
            if self.silence_frames == 1:
                self.state = AudioSessionState.END_OF_TURN_PENDING
                events.append("vad.speech.ended")
        elif self.state == AudioSessionState.END_OF_TURN_PENDING:
            self.silence_frames += 1
            if self.silence_frames >= 40:
                self.state = AudioSessionState.COMPLETED
                events.append("vad.turn.completed")
        return events, probability
