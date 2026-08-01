import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


async def test_terminal_cleanup_releases_duplicate_index() -> None:
    async def publish(*_args: object) -> None: pass
    request = TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish)
    await registry.submit(request)
    await asyncio.sleep(0)
    await registry.cleanup_terminal()
    assert await registry.get(request.transcription_id, request.owner_id, request.session_id, request.connection_id) is None


async def test_new_submission_prunes_terminal_jobs_without_manual_cleanup() -> None:
    async def publish(*_args: object) -> None: pass

    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish, maximum_queued=1)
    first = TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    await registry.submit(first)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    second = TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    await registry.submit(second)

    assert await registry.get(first.transcription_id, first.owner_id, first.session_id, first.connection_id) is None
