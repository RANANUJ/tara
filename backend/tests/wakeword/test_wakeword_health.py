from tara_api.domain.wakeword import WakeWordError, WakeWordState
from tara_api.wakeword.fake import FakeWakeWordBehavior, FakeWakeWordDetector
from tara_api.wakeword.health import LocalWakeWordHealthProvider

from .conftest import configuration


async def test_health_reports_disabled_and_honest_fake_development_capabilities() -> None:
    disabled = await LocalWakeWordHealthProvider(configuration(enabled=False, provider="disabled"), None, environment="test", timeout_seconds=0.1).snapshot()
    assert disabled.state is WakeWordState.DISABLED
    fake = await LocalWakeWordHealthProvider(configuration(), FakeWakeWordDetector(), environment="development", timeout_seconds=0.1).snapshot()
    assert fake.provider == "fake-development"
    assert fake.offline_capable is True
    assert fake.native_background_supported is False
    assert fake.screen_off_supported is False
    assert fake.locked_device_supported is False


async def test_health_is_non_activating_and_sanitizes_unavailability() -> None:
    detector = FakeWakeWordDetector((FakeWakeWordBehavior(unavailable=True),))
    snapshot = await LocalWakeWordHealthProvider(configuration(), detector, environment="test", timeout_seconds=0.1).snapshot()
    assert snapshot.ready is False
    assert snapshot.diagnostic_code is WakeWordError.PROVIDER_UNAVAILABLE
    assert detector.calls == 0
