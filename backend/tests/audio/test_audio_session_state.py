"""Audio session state-machine tests."""

from uuid import uuid4

import pytest

from tara_api.domain.audio import AudioFrame, AudioSessionState
from tara_api.transport.audio import CANONICAL_FORMAT, AudioSession


class FixedVad:
    def __init__(self, *values: float) -> None:
        self.values = iter(values)

    def speech_probability(self, _frame: AudioFrame, _format: object) -> float:
        return next(self.values)


def _frame(session_id: object, sequence: int) -> AudioFrame:
    return AudioFrame(session_id, sequence, bytes(CANONICAL_FORMAT.frame_bytes))  # type: ignore[arg-type]


def test_state_progresses_from_starting_to_completed() -> None:
    session_id = uuid4()
    session = AudioSession(session_id)
    assert session.state == AudioSessionState.STARTING
    session.negotiate(CANONICAL_FORMAT)
    assert session.state == AudioSessionState.LISTENING
    detector = FixedVad(1, 1, 0, *([0] * 39))
    events: list[str] = []
    for sequence in range(42):
        current_events, _ = session.ingest(_frame(session_id, sequence), detector)
        events.extend(current_events)
    assert session.state == AudioSessionState.COMPLETED
    assert events == ["vad.speech.started", "vad.speech.ended", "vad.turn.completed"]


def test_invalid_transition_and_repeated_terminal_operations_are_safe() -> None:
    session = AudioSession(uuid4())
    with pytest.raises(ValueError):
        session.ingest(_frame(session.session_id, 0), FixedVad(0))
    session.cancel()
    session.cancel()
    assert session.state == AudioSessionState.CANCELED
    assert session.stop() == []


def test_completed_or_canceled_session_rejects_frames() -> None:
    session = AudioSession(uuid4())
    session.negotiate(CANONICAL_FORMAT)
    session.stop()
    with pytest.raises(ValueError):
        session.ingest(_frame(session.session_id, 0), FixedVad(0))
