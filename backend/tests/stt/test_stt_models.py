from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.domain.stt import FinalTranscript, TranscriptionConfidence, TranscriptionRequest, TranscriptLanguage, TranscriptSegment


def test_confidence_language_and_transcript_bounds() -> None:
    assert TranscriptLanguage("hi").code == "hi"
    assert FinalTranscript("hello", TranscriptLanguage("en"), TranscriptionConfidence(0.5)).confidence is not None
    with pytest.raises(ValueError):
        TranscriptionConfidence(2)
    with pytest.raises(ValueError):
        TranscriptSegment(20, 10, "bad")
    with pytest.raises(ValueError):
        FinalTranscript("x" * 4001, TranscriptLanguage("en"))


def test_request_keeps_identity_binding() -> None:
    identifier = uuid4()
    request = TranscriptionRequest(identifier, uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 320, datetime.now(UTC))
    assert request.transcription_id == identifier
