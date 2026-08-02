from datetime import datetime
from uuid import uuid4

import pytest

from tara_api.config.settings import Settings
from tara_api.domain.audio import AudioFrame
from tara_api.domain.wakeword import WakeWordAudioFrame, WakeWordError, WakeWordFailure, WakeWordState
from tara_api.wakeword.audio import from_m7_audio_frame

from .conftest import ManualWakeWordClock, configuration


def test_configuration_normalizes_phrase_and_validates_boundaries() -> None:
    item = configuration(phrase="  TaRa   Assistant  ")
    assert item.phrase == "tara assistant"
    with pytest.raises(ValueError, match="confidence"):
        configuration(confidence_threshold=1.1)
    with pytest.raises(ValueError, match="debounce or cooldown"):
        configuration(cooldown_seconds=-1)
    with pytest.raises(ValueError):
        WakeWordState("not-a-state")


def test_audio_frame_requires_utc_and_has_no_client_identity_fields() -> None:
    clock = ManualWakeWordClock()
    with pytest.raises(ValueError, match="UTC"):
        WakeWordAudioFrame(0, b"\0" * 640, 16000, 2, 1, 20, datetime.now())
    assert "owner_id" not in WakeWordAudioFrame.__dataclass_fields__
    assert "session_id" not in WakeWordAudioFrame.__dataclass_fields__
    assert "connection_id" not in WakeWordAudioFrame.__dataclass_fields__
    assert clock.now().tzinfo is not None


def test_m7_audio_adapter_accepts_only_the_bound_audio_session() -> None:
    clock = ManualWakeWordClock()
    from .conftest import identity

    item = identity()
    converted = from_m7_audio_frame(item, AudioFrame(item.audio_session_id, 0, b"\0" * 640), clock.now())
    assert converted.sequence == 0
    with pytest.raises(WakeWordFailure) as mismatch:
        from_m7_audio_frame(item, AudioFrame(uuid4(), 0, b"\0" * 640), clock.now())
    assert mismatch.value.code is WakeWordError.STALE_AUDIO_SESSION


def test_settings_reject_production_fake_and_enabled_disabled_provider() -> None:
    with pytest.raises(ValueError, match="fake wake-word"):
        Settings(_env_file=None, environment="production", stt_provider="disabled", wakeword_provider="fake")
    with pytest.raises(ValueError, match="enabled wake word"):
        Settings(_env_file=None, wakeword_enabled=True, wakeword_provider="disabled")
