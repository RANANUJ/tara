import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.health import HealthState
from tara_api.domain.stt import SpeechToTextSession, TranscriptionRequest
from tara_api.stt.health import SttHealthProvider
from tara_api.stt.service import InMemoryTranscriptionJobs


class BlockingSession(SpeechToTextSession):
    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def cancel(self) -> None:
        self.release.set()

    async def results(self):  # type: ignore[no-untyped-def]
        await self.release.wait()
        if False:
            yield None


class BlockingProvider:
    name = "blocking"

    def __init__(self) -> None:
        self.session = BlockingSession()

    async def readiness(self) -> bool:
        return True

    async def start(self, _request: TranscriptionRequest) -> SpeechToTextSession:
        return self.session


def request() -> TranscriptionRequest:
    return TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))


async def test_health_reports_shared_registry_activity() -> None:
    provider = BlockingProvider()

    async def publish(*_args: object) -> None:
        return None

    jobs = InMemoryTranscriptionJobs(provider, publish)
    health = SttHealthProvider(provider, jobs, required=False, environment="test", language_mode="auto", partial_mode="final_only", max_queue=8, max_concurrency=1, timeout_seconds=0.1)
    item = request()
    await jobs.submit(item)
    await asyncio.sleep(0)

    snapshot = await health.snapshot()
    assert snapshot.active_jobs == 1
    assert snapshot.queue_depth == 0
    assert await health.dependency() == (HealthState.HEALTHY, None)

    assert await jobs.cancel(item.transcription_id, item.connection_id, item.owner_id, item.session_id)


async def test_optional_unavailable_stt_degrades_without_blocking_readiness() -> None:
    class UnavailableProvider(BlockingProvider):
        async def readiness(self) -> bool:
            return False

    provider = UnavailableProvider()
    async def publish(*_args: object) -> None:
        return None
    health = SttHealthProvider(provider, InMemoryTranscriptionJobs(provider, publish), required=False, environment="test", language_mode="auto", partial_mode="final_only", max_queue=8, max_concurrency=1, timeout_seconds=0.1)

    assert await health.dependency() == (HealthState.DEGRADED, None)
