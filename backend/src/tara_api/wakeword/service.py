"""Bounded foreground-only wake-word application service."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.wakeword import (
    WakeWordAudioFrame,
    WakeWordClock,
    WakeWordConfiguration,
    WakeWordDetectionRequest,
    WakeWordDetectionResult,
    WakeWordDetector,
    WakeWordError,
    WakeWordEvent,
    WakeWordFailure,
    WakeWordSessionIdentity,
    WakeWordSessionValidator,
    WakeWordState,
)


class SystemWakeWordClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(slots=True)
class _SessionRecord:
    state: WakeWordState = WakeWordState.IDLE
    positive_detections: int = 0
    last_positive_at: float | None = None
    cooldown_until: float | None = None
    last_sequence: int = -1
    frame_sequences: deque[int] = field(default_factory=deque)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class WakeWordService:
    """Evaluates server-bound foreground PCM frames without retaining raw audio."""

    def __init__(
        self,
        configuration: WakeWordConfiguration,
        detector: WakeWordDetector | None,
        *,
        session_validator: WakeWordSessionValidator | None = None,
        clock: WakeWordClock | None = None,
    ) -> None:
        self._configuration = configuration
        self._detector = detector
        self._session_validator = session_validator
        self._clock = clock or SystemWakeWordClock()
        self._sessions: dict[WakeWordSessionIdentity, _SessionRecord] = {}
        self._sessions_lock = asyncio.Lock()

    async def begin(self, identity: WakeWordSessionIdentity, *, foreground_active: bool) -> WakeWordState:
        if not self._configuration.enabled:
            return WakeWordState.DISABLED
        if not foreground_active:
            raise WakeWordFailure(WakeWordError.FOREGROUND_REQUIRED)
        if self._detector is None:
            raise WakeWordFailure(WakeWordError.PROVIDER_NOT_CONFIGURED)
        await self._require_active_session(identity)
        async with self._sessions_lock:
            self._sessions[identity] = _SessionRecord(state=WakeWordState.LISTENING)
        return WakeWordState.LISTENING

    async def ingest(
        self,
        identity: WakeWordSessionIdentity,
        frame: WakeWordAudioFrame,
        *,
        foreground_active: bool,
        tts_playing: bool = False,
    ) -> WakeWordEvent | None:
        if not self._configuration.enabled:
            return None
        if not foreground_active:
            raise WakeWordFailure(WakeWordError.FOREGROUND_REQUIRED)
        if self._detector is None:
            raise WakeWordFailure(WakeWordError.PROVIDER_NOT_CONFIGURED)
        await self._require_active_session(identity)
        record = await self._record(identity)
        async with record.lock:
            self._validate_frame(frame)
            if frame.sequence != record.last_sequence + 1:
                raise WakeWordFailure(WakeWordError.INVALID_AUDIO_FRAME)
            record.last_sequence = frame.sequence
            now = self._clock.monotonic()
            if record.cooldown_until is not None and now < record.cooldown_until:
                record.state = WakeWordState.COOLDOWN
                return None
            if record.cooldown_until is not None:
                record.cooldown_until = None
            if tts_playing and self._configuration.suspend_during_tts:
                self._reset_detection(record)
                record.state = WakeWordState.LISTENING
                return None
            self._buffer_frame(record, frame.sequence)
            record.state = WakeWordState.DETECTING
            request = WakeWordDetectionRequest(identity, frame, self._configuration.phrase, self._configuration.language_mode, self._clock.now())
            try:
                result = await self._detector.detect(request)
            except asyncio.CancelledError:
                self._reset_detection(record)
                record.state = WakeWordState.CANCELED
                raise
            except WakeWordFailure:
                self._reset_detection(record)
                record.state = WakeWordState.LISTENING
                raise
            except Exception as error:
                self._reset_detection(record)
                record.state = WakeWordState.LISTENING
                raise WakeWordFailure(WakeWordError.INTERNAL_WAKEWORD_ERROR) from error
            event = self._evaluate(record, identity, result, now)
            return event

    async def cancel(self, identity: WakeWordSessionIdentity) -> None:
        async with self._sessions_lock:
            record = self._sessions.pop(identity, None)
        if record is not None:
            async with record.lock:
                self._reset_detection(record)
                record.state = WakeWordState.CANCELED

    async def clear_connection(self, connection_id: object) -> None:
        await self._clear_matching(lambda identity: identity.connection_id == connection_id)

    async def clear_session(self, owner_id: object, session_id: object) -> None:
        await self._clear_matching(lambda identity: identity.owner_id == owner_id and identity.session_id == session_id)

    async def clear_owner(self, owner_id: object) -> None:
        await self._clear_matching(lambda identity: identity.owner_id == owner_id)

    async def clear_audio_session(self, identity: WakeWordSessionIdentity) -> None:
        await self.cancel(identity)

    async def state(self, identity: WakeWordSessionIdentity) -> WakeWordState:
        record = await self._record_or_none(identity)
        return record.state if record is not None else WakeWordState.IDLE

    async def buffered_frame_count(self, identity: WakeWordSessionIdentity) -> int:
        record = await self._record_or_none(identity)
        if record is None:
            return 0
        async with record.lock:
            return len(record.frame_sequences)

    async def _clear_matching(self, predicate: Callable[[WakeWordSessionIdentity], bool]) -> None:
        async with self._sessions_lock:
            matches = tuple(identity for identity in self._sessions if predicate(identity))
            records = tuple(self._sessions.pop(identity) for identity in matches)
        for record in records:
            async with record.lock:
                self._reset_detection(record)
                record.state = WakeWordState.CANCELED

    async def _record(self, identity: WakeWordSessionIdentity) -> _SessionRecord:
        record = await self._record_or_none(identity)
        if record is None:
            raise WakeWordFailure(WakeWordError.STALE_AUDIO_SESSION)
        return record

    async def _record_or_none(self, identity: WakeWordSessionIdentity) -> _SessionRecord | None:
        async with self._sessions_lock:
            return self._sessions.get(identity)

    async def _require_active_session(self, identity: WakeWordSessionIdentity) -> None:
        if self._session_validator is not None and not await self._session_validator.is_owner_session_active(identity.owner_id, identity.session_id):
            await self.clear_session(identity.owner_id, identity.session_id)
            raise WakeWordFailure(WakeWordError.SESSION_INVALIDATED)

    def _validate_frame(self, frame: WakeWordAudioFrame) -> None:
        if frame.sample_rate != 16000 or frame.sample_width_bytes != 2 or frame.channels != 1 or frame.duration_ms != self._configuration.frame_duration_ms:
            raise WakeWordFailure(WakeWordError.UNSUPPORTED_AUDIO_FORMAT)
        age = (self._clock.now() - frame.captured_at).total_seconds()
        if age < 0 or age > self._configuration.maximum_frame_age_seconds:
            raise WakeWordFailure(WakeWordError.STALE_AUDIO_SESSION)

    def _buffer_frame(self, record: _SessionRecord, sequence: int) -> None:
        record.frame_sequences.append(sequence)
        while len(record.frame_sequences) > self._configuration.maximum_buffered_frames:
            record.frame_sequences.popleft()

    def _evaluate(self, record: _SessionRecord, identity: WakeWordSessionIdentity, result: WakeWordDetectionResult, now: float) -> WakeWordEvent | None:
        detector_name = self._detector.name if self._detector is not None else ""
        if not isinstance(result, WakeWordDetectionResult) or result.provider != detector_name:
            self._reset_detection(record)
            record.state = WakeWordState.LISTENING
            raise WakeWordFailure(WakeWordError.INVALID_DETECTOR_RESPONSE)
        confidence = result.confidence
        if not result.detected or confidence is None or confidence.value < self._configuration.confidence_threshold:
            self._reset_detection(record)
            record.state = WakeWordState.LISTENING
            return None
        if record.last_positive_at is None or now - record.last_positive_at > self._configuration.debounce_seconds:
            record.positive_detections = 0
        record.positive_detections += 1
        record.last_positive_at = now
        if record.positive_detections < self._configuration.minimum_consecutive_detections:
            record.state = WakeWordState.LISTENING
            return None
        record.state = WakeWordState.TRIGGERED
        record.cooldown_until = now + self._configuration.cooldown_seconds
        self._reset_detection(record, retain_cooldown=True)
        return WakeWordEvent(uuid4(), identity, confidence, self._clock.now())

    @staticmethod
    def _reset_detection(record: _SessionRecord, *, retain_cooldown: bool = False) -> None:
        record.positive_detections = 0
        record.last_positive_at = None
        record.frame_sequences.clear()
        if not retain_cooldown:
            record.cooldown_until = None
