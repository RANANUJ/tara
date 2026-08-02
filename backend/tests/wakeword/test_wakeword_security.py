import logging

import pytest

from tara_api.domain.wakeword import WakeWordError, WakeWordFailure
from tara_api.observability.logging import JsonFormatter
from tara_api.wakeword.fake import FakeWakeWordBehavior, FakeWakeWordDetector
from tara_api.wakeword.service import WakeWordService

from .conftest import ManualWakeWordClock, configuration, frame, identity


async def test_failures_are_sanitized_and_service_never_logs_raw_audio(caplog: pytest.LogCaptureFixture) -> None:
    clock = ManualWakeWordClock()
    service = WakeWordService(configuration(minimum_consecutive_detections=1), FakeWakeWordDetector((FakeWakeWordBehavior(unavailable=True),)), clock=clock)
    item = identity()
    await service.begin(item, foreground_active=True)
    with caplog.at_level(logging.INFO, logger="tara_api"), pytest.raises(WakeWordFailure) as failure:
        await service.ingest(item, frame(clock), foreground_active=True)
    assert failure.value.code is WakeWordError.PROVIDER_UNAVAILABLE
    assert str(failure.value) == "Wake-word detection could not be completed."
    assert not caplog.records


def test_structured_logging_redacts_wake_audio_and_sensitive_fields() -> None:
    formatter = JsonFormatter(("secret-token",))
    record = logging.LogRecord("tara_api", logging.INFO, __file__, 1, "wake", (), None)
    record.event_data = {"audio_frame": b"pcm-canary", "model_path": "C:/private", "token": "secret-token", "provider": "fake"}
    rendered = formatter.format(record)
    assert "pcm-canary" not in rendered
    assert "C:/private" not in rendered
    assert "secret-token" not in rendered
    assert "fake" in rendered
