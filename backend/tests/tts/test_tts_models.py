from datetime import datetime
from uuid import uuid4

import pytest

from tara_api.domain.tts import (
    SpeechAudioChunk,
    SpeechEncoding,
    SpeechFormat,
    SpeechLanguage,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechSynthesisState,
    SpeechTimingMetadata,
    SpeechUsageMetadata,
    SpeechVoice,
)

from .conftest import request


def test_valid_request_and_final_audio_are_typed() -> None:
    item = request()
    audio = b"\0\0" * 220
    result = SpeechSynthesisResult(
        item.synthesis_id,
        audio,
        item.output_format,
        220,
        SpeechTimingMetadata(1, 10),
        SpeechUsageMetadata(len(item.text), len(audio)),
        item.created_at,
        (SpeechAudioChunk(0, audio, True),),
    )

    assert result.sample_count == 220
    assert item.language is SpeechLanguage.ENGLISH


@pytest.mark.parametrize(
    "factory",
    (
        lambda: SpeechFormat(sample_rate=44100),
        lambda: SpeechFormat(channels=2),
        lambda: SpeechFormat(bit_depth=24),
        lambda: SpeechVoice(""),
        lambda: SpeechAudioChunk(-1, b"\0\0"),
    ),
)
def test_invalid_format_and_chunk_metadata_are_rejected(factory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        factory()


def test_invalid_text_timestamp_and_audio_metadata_are_rejected() -> None:
    with pytest.raises(ValueError):
        SpeechSynthesisRequest(uuid4(), uuid4(), uuid4(), "", SpeechVoice("voice"), SpeechLanguage.ENGLISH, SpeechFormat(), datetime.now())
    item = request()
    with pytest.raises(ValueError):
        SpeechSynthesisResult(
            item.synthesis_id,
            b"\0",
            item.output_format,
            1,
            SpeechTimingMetadata(0, 0),
            SpeechUsageMetadata(1, 1),
            item.created_at,
        )
    assert SpeechEncoding.PCM_S16LE.value == "pcm_s16le"
    with pytest.raises(ValueError):
        SpeechSynthesisState("invalid")
