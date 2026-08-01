"""Binary audio framing validation tests."""

from uuid import uuid4

import pytest

from tara_api.domain.audio import AudioFrame
from tara_api.transport.audio import CANONICAL_FORMAT, FRAME_MAGIC, decode_frame, encode_frame


def _frame(sequence: int = 0) -> AudioFrame:
    return AudioFrame(uuid4(), sequence, bytes(CANONICAL_FORMAT.frame_bytes))


def test_canonical_frame_round_trips() -> None:
    frame = _frame(7)
    assert decode_frame(encode_frame(frame)) == frame


@pytest.mark.parametrize("data", [b"", b"TAR", FRAME_MAGIC + bytes(3)])
def test_malformed_or_truncated_header_is_rejected(data: bytes) -> None:
    with pytest.raises(ValueError):
        decode_frame(data)


@pytest.mark.parametrize("payload", [b"", bytes(CANONICAL_FORMAT.frame_bytes - 1), bytes(CANONICAL_FORMAT.frame_bytes + 1)])
def test_empty_or_mismatched_payload_is_rejected(payload: bytes) -> None:
    with pytest.raises(ValueError):
        decode_frame(FRAME_MAGIC + uuid4().bytes + (0).to_bytes(4, "big") + payload)


def test_oversized_frame_and_negative_sequence_are_rejected() -> None:
    with pytest.raises(ValueError):
        decode_frame(bytes(700))
    with pytest.raises(ValueError):
        encode_frame(_frame(-1))
