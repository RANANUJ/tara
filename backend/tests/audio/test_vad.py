"""Deterministic VAD behavior without model downloads."""

from uuid import uuid4

import pytest

from tara_api.domain.audio import AudioFrame, AudioSessionState
from tara_api.transport.audio import CANONICAL_FORMAT, AudioSession, DeterministicVad


def _payload(amplitude: int) -> bytes:
    return amplitude.to_bytes(2, "little", signed=True) * (CANONICAL_FORMAT.frame_bytes // 2)


def _session() -> AudioSession:
    session = AudioSession(uuid4())
    session.negotiate(CANONICAL_FORMAT)
    return session


def test_silence_and_short_noise_do_not_start_speech() -> None:
    session = _session()
    detector = DeterministicVad()
    assert session.ingest(AudioFrame(session.session_id, 0, _payload(0)), detector)[0] == []
    assert session.ingest(AudioFrame(session.session_id, 1, _payload(10000)), detector)[0] == []
    assert session.ingest(AudioFrame(session.session_id, 2, _payload(0)), detector)[0] == []
    assert session.state == AudioSessionState.LISTENING


def test_valid_speech_starts_once_and_end_boundary_is_exact() -> None:
    session = _session()
    detector = DeterministicVad()
    assert session.ingest(AudioFrame(session.session_id, 0, _payload(10000)), detector)[0] == []
    assert session.ingest(AudioFrame(session.session_id, 1, _payload(10000)), detector)[0] == ["vad.speech.started"]
    assert session.ingest(AudioFrame(session.session_id, 2, _payload(0)), detector)[0] == ["vad.speech.ended"]
    for sequence in range(3, 41):
        assert session.ingest(AudioFrame(session.session_id, sequence, _payload(0)), detector)[0] == []
    assert session.ingest(AudioFrame(session.session_id, 41, _payload(0)), detector)[0] == ["vad.turn.completed"]


def test_vad_failure_fails_session_safely() -> None:
    class BrokenVad:
        def speech_probability(self, _frame: AudioFrame, _format: object) -> float:
            raise RuntimeError("provider detail")

    session = _session()
    with pytest.raises(ValueError, match="voice activity detection failed"):
        session.ingest(AudioFrame(session.session_id, 0, _payload(0)), BrokenVad())
    assert session.state == AudioSessionState.FAILED
