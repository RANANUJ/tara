"""Bounded PCM framing and deterministic M7 VAD state flow."""

import math
import struct
from dataclasses import dataclass, field
from uuid import UUID

from tara_api.domain.audio import AudioFormat, AudioFrame, AudioSessionState, VoiceActivityDetector

FRAME_MAGIC = b"TAR1"
FRAME_HEADER_BYTES = 24
CANONICAL_FORMAT = AudioFormat()
MAX_AUDIO_FRAME_BYTES = FRAME_HEADER_BYTES + CANONICAL_FORMAT.frame_bytes
MIN_SPEECH_FRAMES = 2
END_OF_TURN_SILENCE_FRAMES = 40
MAX_UTTERANCE_FRAMES = 1500
MAX_SESSION_FRAMES = 3000


def decode_frame(data: bytes) -> AudioFrame:
    if len(data) < FRAME_HEADER_BYTES or data[:4] != FRAME_MAGIC:
        raise ValueError("invalid audio frame")
    if len(data) > MAX_AUDIO_FRAME_BYTES:
        raise ValueError("audio frame is too large")
    session_id = UUID(bytes=data[4:20])
    sequence = struct.unpack("!I", data[20:24])[0]
    payload = data[24:]
    if len(payload) != CANONICAL_FORMAT.frame_bytes:
        raise ValueError("invalid audio payload length")
    return AudioFrame(session_id, sequence, payload)


def encode_frame(frame: AudioFrame) -> bytes:
    if frame.sequence < 0:
        raise ValueError("invalid audio frame sequence")
    if len(frame.payload) != CANONICAL_FORMAT.frame_bytes:
        raise ValueError("invalid audio payload length")
    return FRAME_MAGIC + frame.audio_session_id.bytes + struct.pack("!I", frame.sequence) + frame.payload


class DeterministicVad:
    def __init__(self, threshold: float = 0.02) -> None:
        self._threshold = threshold

    def speech_probability(self, frame: AudioFrame, audio_format: AudioFormat) -> float:
        audio_format.validate()
        rms = pcm_rms_level(frame.payload, audio_format)
        return min(1.0, max(0.0, rms / max(self._threshold, 0.0001)))


def pcm_rms_level(payload: bytes, audio_format: AudioFormat = CANONICAL_FORMAT) -> float:
    """Return a finite normalized RMS level for canonical PCM without retention."""
    if len(payload) != audio_format.frame_bytes:
        raise ValueError("invalid PCM payload")
    samples = struct.unpack(f"<{len(payload) // 2}h", payload)
    if not samples:
        raise ValueError("empty PCM payload")
    return min(1.0, max(0.0, math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768))


@dataclass(slots=True)
class AudioLevelMeter:
    """Bound and smooth visual levels without retaining PCM."""

    smoothing: float = 0.25
    emit_every_frames: int = 5
    _frames_since_emit: int = 0
    _level: float = 0.0

    def observe(self, level: float) -> float | None:
        safe_level = level if math.isfinite(level) else 0.0
        safe_level = min(1.0, max(0.0, safe_level))
        self._level += (safe_level - self._level) * self.smoothing
        self._frames_since_emit += 1
        if self._frames_since_emit < self.emit_every_frames:
            return None
        self._frames_since_emit = 0
        return self._level

    def reset(self) -> None:
        self._frames_since_emit = 0
        self._level = 0.0


@dataclass(slots=True)
class AudioSession:
    session_id: UUID
    state: AudioSessionState = AudioSessionState.STARTING
    format_negotiated: bool = False
    last_sequence: int = -1
    speech_frames: int = 0
    silence_frames: int = 0
    utterance_frames: int = 0
    total_frames: int = 0
    level_meter: AudioLevelMeter = field(default_factory=AudioLevelMeter)

    def negotiate(self, audio_format: AudioFormat) -> None:
        audio_format.validate()
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
        self.total_frames += 1
        if self.total_frames > MAX_SESSION_FRAMES:
            self.state = AudioSessionState.COMPLETED
            self.level_meter.reset()
            return ["vad.turn.completed"], 0.0
        try:
            probability = detector.speech_probability(frame, CANONICAL_FORMAT)
        except Exception as error:
            self.fail()
            raise ValueError("voice activity detection failed") from error
        if not math.isfinite(probability):
            self.fail()
            raise ValueError("voice activity detection returned an invalid value")
        events: list[str] = []
        if probability >= 1:
            self.speech_frames += 1
            self.silence_frames = 0
            self.utterance_frames += 1
            if self.utterance_frames > MAX_UTTERANCE_FRAMES:
                self.state = AudioSessionState.COMPLETED
                events.append("vad.turn.completed")
                return events, probability
            if self.state == AudioSessionState.LISTENING and self.speech_frames >= 2:
                self.state = AudioSessionState.SPEECH_DETECTED
                events.append("vad.speech.started")
            elif self.state == AudioSessionState.END_OF_TURN_PENDING:
                self.state = AudioSessionState.SPEECH_DETECTED
        elif self.state == AudioSessionState.SPEECH_DETECTED:
            self.speech_frames = 0
            self.silence_frames += 1
            if self.silence_frames == 1:
                self.state = AudioSessionState.END_OF_TURN_PENDING
                events.append("vad.speech.ended")
        elif self.state == AudioSessionState.END_OF_TURN_PENDING:
            self.silence_frames += 1
            if self.silence_frames >= 40:
                self.state = AudioSessionState.COMPLETED
                events.append("vad.turn.completed")
        else:
            self.speech_frames = 0
        return events, probability

    def audio_level(self, probability: float) -> float | None:
        if self.state in {AudioSessionState.CANCELED, AudioSessionState.COMPLETED, AudioSessionState.FAILED}:
            return None
        return self.level_meter.observe(probability)

    def stop(self) -> list[str]:
        if self.state in {AudioSessionState.CANCELED, AudioSessionState.COMPLETED, AudioSessionState.FAILED}:
            return []
        events = ["vad.speech.ended"] if self.state == AudioSessionState.SPEECH_DETECTED else []
        self.state = AudioSessionState.COMPLETED
        events.append("vad.turn.completed")
        self.level_meter.reset()
        return events

    def cancel(self) -> None:
        if self.state not in {AudioSessionState.COMPLETED, AudioSessionState.FAILED}:
            self.state = AudioSessionState.CANCELED
        self.level_meter.reset()

    def fail(self) -> None:
        self.state = AudioSessionState.FAILED
        self.level_meter.reset()
