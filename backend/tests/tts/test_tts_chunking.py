import pytest

from tara_api.domain.tts import SpeechSynthesisError, SpeechSynthesisFailure
from tara_api.tts.chunking import chunk_synthesized_audio
from tara_api.tts.validation import validated_result

from .conftest import request


def test_pcm_chunking_is_ordered_aligned_and_lossless() -> None:
    source = request()
    result = validated_result(source, b"\0" * 10, synthesis_duration_ms=1)
    chunks = chunk_synthesized_audio(result, 4)

    assert [item.sequence for item in chunks] == [0, 1, 2]
    assert [item.byte_offset for item in chunks] == [0, 4, 8]
    assert [item.byte_length for item in chunks] == [4, 4, 2]
    assert sum(item.is_final for item in chunks) == 1
    assert b"".join(item.audio for item in chunks) == result.audio


def test_invalid_or_wav_fragment_chunking_is_rejected() -> None:
    source = request()
    result = validated_result(source, b"\0" * 8, synthesis_duration_ms=1)
    with pytest.raises(SpeechSynthesisFailure) as failure:
        chunk_synthesized_audio(result, 3)
    assert failure.value.code is SpeechSynthesisError.INVALID_AUDIO_METADATA
