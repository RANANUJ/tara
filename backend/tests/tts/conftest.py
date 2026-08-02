"""Shared immutable TTS fixtures."""

from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.tts import SpeechFormat, SpeechLanguage, SpeechSynthesisRequest, SpeechVoice


def request(*, text: str = "Hello Tara", output_format: SpeechFormat | None = None) -> SpeechSynthesisRequest:
    return SpeechSynthesisRequest(
        uuid4(),
        uuid4(),
        uuid4(),
        text,
        SpeechVoice("local-voice"),
        SpeechLanguage.ENGLISH,
        output_format or SpeechFormat(),
        datetime.now(UTC),
    )
