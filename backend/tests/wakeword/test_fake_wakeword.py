import asyncio

import pytest

from tara_api.domain.wakeword import WakeWordDetectionRequest, WakeWordError, WakeWordFailure
from tara_api.wakeword.fake import FakeWakeWordBehavior, FakeWakeWordDetector

from .conftest import ManualWakeWordClock, frame, identity


def request() -> WakeWordDetectionRequest:
    clock = ManualWakeWordClock()
    return WakeWordDetectionRequest(identity(), frame(clock), "tara", "auto", clock.now())


async def test_fake_detector_is_deterministic_for_trigger_no_trigger_and_repeated_results() -> None:
    detector = FakeWakeWordDetector((FakeWakeWordBehavior(True, 0.9), FakeWakeWordBehavior(False)), repeat=True)
    first = await detector.detect(request())
    second = await detector.detect(request())
    third = await detector.detect(request())
    assert (first.detected, first.confidence.value if first.confidence else None) == (True, 0.9)
    assert second.detected is False
    assert third.detected is True


async def test_fake_detector_supports_delay_cancellation_unavailability_and_malformed_response() -> None:
    delayed = FakeWakeWordDetector((FakeWakeWordBehavior(delay_seconds=10),))
    task = asyncio.create_task(delayed.detect(request()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(WakeWordFailure) as unavailable:
        await FakeWakeWordDetector((FakeWakeWordBehavior(unavailable=True),)).detect(request())
    assert unavailable.value.code is WakeWordError.PROVIDER_UNAVAILABLE
    malformed = await FakeWakeWordDetector((FakeWakeWordBehavior(malformed_result=True),)).detect(request())
    assert not hasattr(malformed, "detected")
