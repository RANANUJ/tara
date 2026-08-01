"""M7 deliberately retains no raw audio buffers."""

from uuid import uuid4

from tara_api.domain.audio import AudioFrame, AudioSessionState
from tara_api.transport import audio


class SilentVad:
    def speech_probability(self, _frame: AudioFrame, _format: object) -> float:
        return 0


def test_audio_session_retains_no_pcm_and_stops_at_bounded_duration(monkeypatch: object) -> None:
    monkeypatch.setattr(audio, "MAX_SESSION_FRAMES", 2)  # type: ignore[attr-defined]
    session = audio.AudioSession(uuid4())
    session.negotiate(audio.CANONICAL_FORMAT)
    detector = SilentVad()
    for sequence in range(2):
        session.ingest(AudioFrame(session.session_id, sequence, bytes(audio.CANONICAL_FORMAT.frame_bytes)), detector)
    session.ingest(AudioFrame(session.session_id, 2, bytes(audio.CANONICAL_FORMAT.frame_bytes)), detector)
    assert session.state == AudioSessionState.COMPLETED
    assert not hasattr(session, "payload")


def test_stop_and_cancel_clear_transient_level_state() -> None:
    session = audio.AudioSession(uuid4())
    session.negotiate(audio.CANONICAL_FORMAT)
    session.level_meter.observe(1)
    session.cancel()
    assert session.level_meter._level == 0  # noqa: SLF001
