import pytest

from tara_api.domain.wakeword import WakeWordError, WakeWordFailure, WakeWordState
from tara_api.wakeword.fake import FakeWakeWordBehavior, FakeWakeWordDetector
from tara_api.wakeword.service import WakeWordService

from .conftest import ActiveSessions, ManualWakeWordClock, configuration, frame, identity


async def test_disabled_service_cannot_trigger_or_create_agent_work() -> None:
    clock = ManualWakeWordClock()
    item = identity()
    service = WakeWordService(configuration(enabled=False, provider="disabled"), None, clock=clock)
    assert await service.begin(item, foreground_active=True) is WakeWordState.DISABLED
    assert await service.ingest(item, frame(clock), foreground_active=True) is None


async def test_consecutive_valid_detections_emit_one_typed_event() -> None:
    clock = ManualWakeWordClock()
    item = identity()
    detector = FakeWakeWordDetector((FakeWakeWordBehavior(True, 0.9),), repeat=True)
    service = WakeWordService(configuration(), detector, session_validator=ActiveSessions(), clock=clock)
    await service.begin(item, foreground_active=True)
    assert await service.ingest(item, frame(clock, 0), foreground_active=True) is None
    event = await service.ingest(item, frame(clock, 1), foreground_active=True)
    assert event is not None
    assert event.identity == item
    assert await service.ingest(item, frame(clock, 2), foreground_active=True) is None
    assert detector.calls == 2


async def test_invalid_result_and_provider_failure_are_safe_and_service_recovers() -> None:
    clock = ManualWakeWordClock()
    item = identity()
    malformed = WakeWordService(configuration(minimum_consecutive_detections=1), FakeWakeWordDetector((FakeWakeWordBehavior(malformed_result=True),)), clock=clock)
    await malformed.begin(item, foreground_active=True)
    with pytest.raises(WakeWordFailure) as error:
        await malformed.ingest(item, frame(clock), foreground_active=True)
    assert error.value.code is WakeWordError.INVALID_DETECTOR_RESPONSE
    detector = FakeWakeWordDetector((FakeWakeWordBehavior(unavailable=True), FakeWakeWordBehavior(True, 0.9)))
    recovered = WakeWordService(configuration(minimum_consecutive_detections=1), detector, clock=clock)
    second = identity()
    await recovered.begin(second, foreground_active=True)
    with pytest.raises(WakeWordFailure):
        await recovered.ingest(second, frame(clock), foreground_active=True)
    assert await recovered.ingest(second, frame(clock, 1), foreground_active=True) is not None
