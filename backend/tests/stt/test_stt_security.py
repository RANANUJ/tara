from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


async def test_publisher_receives_no_audio_or_session_credentials() -> None:
    payloads: list[dict[str, object]] = []
    async def publish(_job: object, _event: str, payload: dict[str, object]) -> None:
        payloads.append(payload)
    request = TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\x01\x02" * 640, datetime.now(UTC))
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish)
    await registry.submit(request)
    import asyncio
    await asyncio.sleep(0)
    assert all("pcm" not in payload and "token" not in payload for payload in payloads)
