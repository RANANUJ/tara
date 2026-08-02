from datetime import timedelta

import pytest

from tara_api.domain.wakeword import WakeWordError, WakeWordFailure, WakeWordState
from tara_api.wakeword.fake import FakeWakeWordBehavior, FakeWakeWordDetector
from tara_api.wakeword.service import WakeWordService

from .conftest import ManualWakeWordClock, configuration, frame, identity


async def test_threshold_debounce_and_cooldown_are_per_session() -> None:
    clock = ManualWakeWordClock()
    item = identity()
    detector = FakeWakeWordDetector((FakeWakeWordBehavior(True, 0.79), FakeWakeWordBehavior(True, 0.9)), repeat=True)
    service = WakeWordService(configuration(minimum_consecutive_detections=1), detector, clock=clock)
    await service.begin(item, foreground_active=True)
    assert await service.ingest(item, frame(clock, 0), foreground_active=True) is None
    assert await service.ingest(item, frame(clock, 1), foreground_active=True) is not None
    assert await service.state(item) is WakeWordState.TRIGGERED
    assert await service.ingest(item, frame(clock, 2), foreground_active=True) is None
    assert detector.calls == 2
    clock.advance(3.1)
    assert await service.ingest(item, frame(clock, 3), foreground_active=True) is None
    assert await service.ingest(item, frame(clock, 4), foreground_active=True) is not None


async def test_stale_duplicate_and_bounded_frames_are_rejected_or_limited() -> None:
    clock = ManualWakeWordClock()
    item = identity()
    service = WakeWordService(
        configuration(minimum_consecutive_detections=10, maximum_buffered_frames=2),
        FakeWakeWordDetector((FakeWakeWordBehavior(True, 0.9),), repeat=True),
        clock=clock,
    )
    await service.begin(item, foreground_active=True)
    for sequence in range(3):
        assert await service.ingest(item, frame(clock, sequence), foreground_active=True) is None
    assert await service.buffered_frame_count(item) == 2
    with pytest.raises(WakeWordFailure) as duplicate:
        await service.ingest(item, frame(clock, 2), foreground_active=True)
    assert duplicate.value.code is WakeWordError.INVALID_AUDIO_FRAME
    stale = frame(clock, 3, captured_at=clock.now() - timedelta(seconds=3))
    with pytest.raises(WakeWordFailure) as stale_error:
        await service.ingest(item, stale, foreground_active=True)
    assert stale_error.value.code is WakeWordError.STALE_AUDIO_SESSION
