from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import FakeSpeechToTextProvider


async def test_fake_provider_is_deterministic_and_local() -> None:
    request = TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    provider = FakeSpeechToTextProvider()
    session = await provider.start(request)
    results = [item async for item in session.results()]
    assert results[0].text == "test transcript"
    assert results[0].language.code == "en"
