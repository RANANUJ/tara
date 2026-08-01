import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.domain.stt import FinalTranscript, SpeechToTextSession, TranscriptionRequest, TranscriptLanguage
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


def request(connection_id: object | None = None) -> TranscriptionRequest:
    return TranscriptionRequest(uuid4(), uuid4(), uuid4(), connection_id or uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))  # type: ignore[arg-type]


class BlockingSession:
    def __init__(self, provider: "BlockingProvider") -> None:
        self._provider = provider

    async def cancel(self) -> None:
        self._provider.release.set()

    async def results(self):  # type: ignore[no-untyped-def]
        self._provider.active += 1
        self._provider.maximum_active = max(self._provider.maximum_active, self._provider.active)
        try:
            await self._provider.release.wait()
            yield FinalTranscript("done", TranscriptLanguage("en"))
        finally:
            self._provider.active -= 1


class BlockingProvider:
    name = "blocking"

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.active = 0
        self.maximum_active = 0

    async def readiness(self) -> bool:
        return True

    async def start(self, _request: TranscriptionRequest) -> SpeechToTextSession:
        return BlockingSession(self)


async def test_queue_and_connection_limits_reject_without_partial_registration() -> None:
    async def publish(*_args: object) -> None: pass
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish, maximum_queued=1, maximum_per_connection=1)
    first = request()
    await registry.submit(first)
    with pytest.raises(ValueError):
        await registry.submit(request())


async def test_per_session_limit_rejects_another_connection() -> None:
    async def publish(*_args: object) -> None: pass

    session_id = uuid4()
    first = TranscriptionRequest(uuid4(), uuid4(), session_id, uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    second = TranscriptionRequest(uuid4(), uuid4(), session_id, uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish, maximum_per_session=1)

    await registry.submit(first)
    with pytest.raises(ValueError, match="session_job_limit"):
        await registry.submit(second)


async def test_global_concurrency_is_bounded() -> None:
    async def publish(*_args: object) -> None: pass

    provider = BlockingProvider()
    registry = InMemoryTranscriptionJobs(provider, publish, maximum_queued=2, maximum_concurrent=1)
    await registry.submit(request())
    await registry.submit(request())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert provider.maximum_active == 1
    provider.release.set()
    await asyncio.sleep(0)
