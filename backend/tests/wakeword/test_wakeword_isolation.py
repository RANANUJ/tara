import asyncio

import pytest

from tara_api.domain.wakeword import WakeWordError, WakeWordFailure, WakeWordState
from tara_api.wakeword.fake import FakeWakeWordBehavior, FakeWakeWordDetector
from tara_api.wakeword.service import WakeWordService

from .conftest import ActiveSessions, ManualWakeWordClock, configuration, frame, identity


async def test_identity_and_connection_state_are_isolated_and_cleanup_is_idempotent() -> None:
    clock = ManualWakeWordClock()
    first, second = identity(), identity()
    service = WakeWordService(configuration(minimum_consecutive_detections=1), FakeWakeWordDetector((FakeWakeWordBehavior(True, 0.9),), repeat=True), clock=clock)
    await service.begin(first, foreground_active=True)
    await service.begin(second, foreground_active=True)
    assert await service.ingest(first, frame(clock), foreground_active=True) is not None
    assert await service.ingest(second, frame(clock), foreground_active=True) is not None
    await service.clear_connection(first.connection_id)
    await service.clear_connection(first.connection_id)
    assert await service.state(first) is WakeWordState.IDLE
    assert await service.state(second) is WakeWordState.TRIGGERED
    with pytest.raises(WakeWordFailure) as stale:
        await service.ingest(first, frame(clock, 1), foreground_active=True)
    assert stale.value.code is WakeWordError.STALE_AUDIO_SESSION


async def test_session_invalidation_and_concurrent_detection_do_not_cross_sessions() -> None:
    clock = ManualWakeWordClock()
    sessions = ActiveSessions()
    first, second = identity(), identity()
    service = WakeWordService(configuration(minimum_consecutive_detections=1), FakeWakeWordDetector((FakeWakeWordBehavior(True, 0.9),), repeat=True), session_validator=sessions, clock=clock)
    await service.begin(first, foreground_active=True)
    await service.begin(second, foreground_active=True)
    first_event, second_event = await asyncio.gather(service.ingest(first, frame(clock), foreground_active=True), service.ingest(second, frame(clock), foreground_active=True))
    assert first_event is not None and second_event is not None
    sessions.active = False
    with pytest.raises(WakeWordFailure) as inactive:
        await service.ingest(first, frame(clock, 1), foreground_active=True)
    assert inactive.value.code is WakeWordError.SESSION_INVALIDATED
    assert await service.state(second) is WakeWordState.TRIGGERED
