import pytest

from tara_api.stt.service import pcm_duration_ms, pcm_sample_count


def test_pcm_sample_count_and_duration_are_canonical() -> None:
    pcm = b"\0\0" * 16000
    assert pcm_sample_count(pcm) == 16000
    assert pcm_duration_ms(pcm) == 1000


@pytest.mark.parametrize("pcm", [b"", b"\0"])
def test_invalid_pcm_is_rejected(pcm: bytes) -> None:
    with pytest.raises(ValueError):
        pcm_sample_count(pcm)
