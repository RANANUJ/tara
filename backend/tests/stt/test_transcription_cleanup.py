from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


async def test_terminal_cleanup_releases_duplicate_index() -> None:
    async def publish(*_args: object) -> None: pass
    request = TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish)
    await registry.submit(request)
    await __import__("asyncio").sleep(0)
    await registry.cleanup_terminal()
    assert await registry.get(request.transcription_id, request.owner_id, request.session_id, request.connection_id) is None
