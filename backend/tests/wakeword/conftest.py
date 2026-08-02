from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from tara_api.domain.wakeword import WakeWordAudioFrame, WakeWordConfiguration, WakeWordSessionIdentity
from tara_api.wakeword.service import WakeWordClock


class ManualWakeWordClock(WakeWordClock):
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 2, tzinfo=UTC)
        self.current_monotonic = 10.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.current_monotonic

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.current_monotonic += seconds


class ActiveSessions:
    def __init__(self, active: bool = True) -> None:
        self.active = active

    async def is_owner_session_active(self, _owner_id: UUID, _session_id: UUID) -> bool:
        return self.active


def identity() -> WakeWordSessionIdentity:
    return WakeWordSessionIdentity(uuid4(), uuid4(), uuid4(), uuid4())


def frame(clock: ManualWakeWordClock, sequence: int = 0, *, captured_at: datetime | None = None) -> WakeWordAudioFrame:
    return WakeWordAudioFrame(sequence, b"\0" * 640, 16000, 2, 1, 20, captured_at or clock.now())


def configuration(**overrides: object) -> WakeWordConfiguration:
    values: dict[str, object] = {
        "provider": "fake",
        "phrase": "Tara",
        "enabled": True,
        "confidence_threshold": 0.8,
        "minimum_consecutive_detections": 2,
        "cooldown_seconds": 3.0,
        "debounce_seconds": 1.0,
        "frame_duration_ms": 20,
        "maximum_buffered_frames": 2,
        "language_mode": "auto",
        "foreground_only": True,
        "maximum_frame_age_seconds": 2.0,
    }
    values.update(overrides)
    return WakeWordConfiguration(**values)  # type: ignore[arg-type]
