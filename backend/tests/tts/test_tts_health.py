import asyncio
from pathlib import Path

import pytest

from tara_api.domain.tts import SpeechFormat, SpeechProviderState, SpeechSynthesisError, SpeechVoice
from tara_api.tts.fake import FakeTextToSpeechBehavior, FakeTextToSpeechProvider
from tara_api.tts.health import LocalTextToSpeechHealthProvider
from tara_api.tts.piper import PiperTextToSpeechProvider


async def test_tts_health_reports_disabled_fake_and_provider_failure() -> None:
    disabled = await LocalTextToSpeechHealthProvider(None, required=False, environment="test", language_mode="auto", timeout_seconds=0.1).snapshot()
    assert disabled.state is SpeechProviderState.DISABLED
    fake = await LocalTextToSpeechHealthProvider(FakeTextToSpeechProvider(environment="development"), required=False, environment="development", language_mode="auto", timeout_seconds=0.1).snapshot()
    assert fake.provider == "fake-development"
    assert fake.ready is True
    unavailable = await LocalTextToSpeechHealthProvider(FakeTextToSpeechProvider(FakeTextToSpeechBehavior(unavailable=True), environment="test"), required=False, environment="test", language_mode="auto", timeout_seconds=0.1).snapshot()
    assert unavailable.diagnostic_code is SpeechSynthesisError.PROVIDER_UNAVAILABLE


async def test_tts_health_checks_piper_paths_without_synthesizing(tmp_path: Path) -> None:
    missing = PiperTextToSpeechProvider(str(tmp_path / "missing-piper"), str(tmp_path / "voice.onnx"), voice=SpeechVoice("local-voice"), output_format=SpeechFormat())
    snapshot = await LocalTextToSpeechHealthProvider(missing, required=False, environment="test", language_mode="auto", timeout_seconds=0.1).snapshot()
    assert snapshot.state is SpeechProviderState.UNAVAILABLE
    assert snapshot.diagnostic_code is SpeechSynthesisError.VOICE_NOT_AVAILABLE
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    missing_executable = PiperTextToSpeechProvider(str(tmp_path / "missing-piper"), str(model), voice=SpeechVoice("local-voice"), output_format=SpeechFormat())
    executable_snapshot = await LocalTextToSpeechHealthProvider(missing_executable, required=False, environment="test", language_mode="auto", timeout_seconds=0.1).snapshot()
    assert executable_snapshot.diagnostic_code is SpeechSynthesisError.PROVIDER_UNAVAILABLE


async def test_tts_health_timeout_is_bounded_without_synthesis() -> None:
    class SlowProvider(FakeTextToSpeechProvider):
        async def readiness(self):  # type: ignore[no-untyped-def]
            await asyncio.sleep(1)
            return await super().readiness()

    snapshot = await LocalTextToSpeechHealthProvider(SlowProvider(environment="test"), required=False, environment="test", language_mode="auto", timeout_seconds=0.01).snapshot()
    assert snapshot.state is SpeechProviderState.DEGRADED
    assert snapshot.diagnostic_code is SpeechSynthesisError.PROVIDER_TIMEOUT


def test_settings_reject_unsafe_tts_combinations() -> None:
    from tara_api.config.settings import Settings

    with pytest.raises(ValueError, match="fake TTS"):
        Settings(_env_file=None, environment="production", stt_provider="disabled", tts_provider="fake")
    with pytest.raises(ValueError, match="Piper TTS"):
        Settings(_env_file=None, tts_provider="piper")
    with pytest.raises(ValueError, match="ElevenLabs TTS"):
        Settings(_env_file=None, tts_provider="elevenlabs")
