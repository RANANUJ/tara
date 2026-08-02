import pytest

from tara_api.domain.tts import SpeechFormat, SpeechSynthesisError, SpeechSynthesisFailure
from tara_api.tts.validation import normalize_synthesis_text, validated_result

from .conftest import request


def test_text_normalization_is_deterministic_and_rejects_unsafe_text() -> None:
    assert normalize_synthesis_text(" hello\r\n  Tara ") == "hello Tara"
    for value, code in (("   ", SpeechSynthesisError.EMPTY_TEXT), ("bad\0text", SpeechSynthesisError.INVALID_TEXT), (chr(0xD800), SpeechSynthesisError.INVALID_TEXT)):
        with pytest.raises(SpeechSynthesisFailure) as error:
            normalize_synthesis_text(value)
        assert error.value.code is code


def test_provider_audio_validation_rejects_empty_misaligned_and_excessive_audio() -> None:
    item = request()
    for audio, code in ((b"", SpeechSynthesisError.INVALID_AUDIO_RESPONSE), (b"\0", SpeechSynthesisError.INVALID_AUDIO_METADATA), (b"\0" * (8 * 1024 * 1024 + 2), SpeechSynthesisError.AUDIO_TOO_LARGE)):
        with pytest.raises(SpeechSynthesisFailure) as error:
            validated_result(item, audio, synthesis_duration_ms=0)
        assert error.value.code is code
    with pytest.raises(ValueError):
        SpeechFormat(sample_rate=48000)
