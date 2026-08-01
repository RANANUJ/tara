"""Audio cleanup contract tests."""

from uuid import uuid4

from tara_api.domain.audio import AudioSessionState
from tara_api.transport.audio import CANONICAL_FORMAT, AudioSession


def test_stop_and_cancel_are_idempotent_cleanup_operations() -> None:
    stopped = AudioSession(uuid4())
    stopped.negotiate(CANONICAL_FORMAT)
    assert stopped.stop() == ["vad.turn.completed"]
    assert stopped.stop() == []
    assert stopped.state == AudioSessionState.COMPLETED

    canceled = AudioSession(uuid4())
    canceled.negotiate(CANONICAL_FORMAT)
    canceled.cancel()
    canceled.cancel()
    assert canceled.state == AudioSessionState.CANCELED
