"""Frame/session binding and strict ordering tests."""

from uuid import uuid4

import pytest

from tara_api.domain.audio import AudioFrame
from tara_api.transport.audio import CANONICAL_FORMAT, AudioSession


class SilentVad:
    def speech_probability(self, _frame: AudioFrame, _format: object) -> float:
        return 0


def test_wrong_session_duplicate_and_out_of_order_frames_are_rejected() -> None:
    session = AudioSession(uuid4())
    session.negotiate(CANONICAL_FORMAT)
    payload = bytes(CANONICAL_FORMAT.frame_bytes)
    detector = SilentVad()
    with pytest.raises(ValueError):
        session.ingest(AudioFrame(uuid4(), 0, payload), detector)
    session.ingest(AudioFrame(session.session_id, 0, payload), detector)
    with pytest.raises(ValueError):
        session.ingest(AudioFrame(session.session_id, 0, payload), detector)
    with pytest.raises(ValueError):
        session.ingest(AudioFrame(session.session_id, 2, payload), detector)
    session.ingest(AudioFrame(session.session_id, 1, payload), detector)
