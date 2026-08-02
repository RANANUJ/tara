import asyncio

import pytest

from tara_api.domain.tts import SpeechFormat, SpeechSynthesisError, SpeechSynthesisFailure
from tara_api.tts.fake import FakeTextToSpeechBehavior, FakeTextToSpeechProvider

from .conftest import request


async def test_fake_tts_is_deterministic_and_supports_delay() -> None:
    provider = FakeTextToSpeechProvider(environment="test")
    first, second = await provider.synthesize(request()), await provider.synthesize(request())
    assert first.audio == second.audio
    assert first.timing.audio_duration_ms > 0
    assert (await FakeTextToSpeechProvider(FakeTextToSpeechBehavior(delay_seconds=0.001), environment="test").synthesize(request())).audio


@pytest.mark.parametrize(
    ("behavior", "code"),
    (
        (FakeTextToSpeechBehavior(unavailable=True), SpeechSynthesisError.PROVIDER_UNAVAILABLE),
        (FakeTextToSpeechBehavior(malformed_audio=True), SpeechSynthesisError.INVALID_AUDIO_METADATA),
        (FakeTextToSpeechBehavior(excessive_audio=True), SpeechSynthesisError.AUDIO_TOO_LARGE),
        (FakeTextToSpeechBehavior(invalid_metadata=True), SpeechSynthesisError.INVALID_AUDIO_METADATA),
        (FakeTextToSpeechBehavior(unsupported_language=True), SpeechSynthesisError.LANGUAGE_NOT_SUPPORTED),
        (FakeTextToSpeechBehavior(unsupported_format=True), SpeechSynthesisError.FORMAT_NOT_SUPPORTED),
    ),
)
async def test_fake_tts_safe_failures(behavior: FakeTextToSpeechBehavior, code: SpeechSynthesisError) -> None:
    provider = FakeTextToSpeechProvider(behavior, environment="test")
    with pytest.raises(SpeechSynthesisFailure) as error:
        await provider.synthesize(request(output_format=SpeechFormat()))
    assert error.value.code is code


async def test_fake_tts_timeout_and_cancellation() -> None:
    with pytest.raises(SpeechSynthesisFailure) as timed_out:
        await FakeTextToSpeechProvider(FakeTextToSpeechBehavior(delay_seconds=0.02), timeout_seconds=0.01, environment="test").synthesize(request())
    assert timed_out.value.code is SpeechSynthesisError.PROVIDER_TIMEOUT
    task = asyncio.create_task(FakeTextToSpeechProvider(FakeTextToSpeechBehavior(delay_seconds=1), environment="test").synthesize(request()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_fake_tts_rejects_production() -> None:
    with pytest.raises(ValueError):
        FakeTextToSpeechProvider(environment="production")
