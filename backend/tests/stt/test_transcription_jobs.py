import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.stt import TranscriptionRequest, TranscriptionStatus
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


def request() -> TranscriptionRequest:
    return TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))


async def test_duplicate_turn_is_registered_once_and_identity_is_preserved() -> None:
    async def publish(*_args: object) -> None: pass
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish)
    item = request()
    second = TranscriptionRequest(uuid4(), item.owner_id, item.session_id, item.connection_id, item.audio_session_id, item.turn_id, item.pcm16, item.created_at)
    first_job, second_job = await asyncio.gather(registry.submit(item), registry.submit(second))
    assert first_job is second_job
    assert first_job.request.owner_id == item.owner_id
    await asyncio.sleep(0)


async def test_connection_and_session_cancellation_are_isolated() -> None:
    async def publish(*_args: object) -> None: pass
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish)
    first, second = request(), request()
    first_job, second_job = await registry.submit(first), await registry.submit(second)
    assert not await registry.cancel(first.transcription_id, second.connection_id, second.owner_id, second.session_id)
    assert await registry.cancel(first.transcription_id, first.connection_id, first.owner_id, first.session_id)
    assert first_job.status == TranscriptionStatus.CANCELED
    assert second_job.status != TranscriptionStatus.CANCELED
