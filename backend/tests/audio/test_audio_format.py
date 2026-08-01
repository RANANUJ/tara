"""Canonical foreground PCM format tests."""

import pytest

from tara_api.domain.audio import AudioFormat, AudioFormatError
from tara_api.transport.audio import CANONICAL_FORMAT


def test_supported_pcm_format_is_accepted() -> None:
    CANONICAL_FORMAT.validate()


@pytest.mark.parametrize(
    "format",
    [
        AudioFormat(sample_rate=48000),
        AudioFormat(channels=2),
        AudioFormat(sample_width_bytes=4),
        AudioFormat(endianness="big"),
    ],
)
def test_unsupported_pcm_format_is_rejected(format: AudioFormat) -> None:
    with pytest.raises(AudioFormatError):
        format.validate()
