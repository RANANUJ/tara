import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from tara_api.domain.stt import FinalTranscript, PartialTranscript, TranscriptionRequest, TranscriptLanguage
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


def request() -> TranscriptionRequest:
    return TranscriptionRequest(uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))


async def test_lifecycle_events_are_ordered_and_terminal() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    async def publish(_job: object, event: str, payload: dict[str, object]) -> None:
        events.append((event, payload))
    provider = FakeSpeechToTextProvider((PartialTranscript("hello", 1), FinalTranscript("hello world", TranscriptLanguage("en"))))
    registry = InMemoryTranscriptionJobs(provider, publish)
    await registry.submit(request())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert [event[0] for event in events] == ["transcript.started", "transcript.partial", "transcript.final"]
    assert events[-1][1]["is_final"] is True


async def test_canceled_job_emits_no_final() -> None:
    events: list[str] = []
    async def publish(_job: object, event: str, _payload: dict[str, object]) -> None:
        events.append(event)
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish)
    item = request()
    await registry.submit(item)
    assert await registry.cancel(item.transcription_id, item.connection_id, item.owner_id, item.session_id)
    await asyncio.sleep(0)
    assert "transcript.final" not in events


async def test_provider_without_a_final_result_emits_a_sanitized_error() -> None:
    events: list[tuple[str, dict[str, object]]] = []

    async def publish(_job: object, event: str, payload: dict[str, object]) -> None:
        events.append((event, payload))

    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider((PartialTranscript("hello", 1),)), publish)
    await registry.submit(request())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert events[-1] == ("transcript.error", {"code": "provider_failure"})


async def test_registry_timeout_emits_a_terminal_safe_error() -> None:
    class SlowSession:
        async def cancel(self) -> None:
            return None

        async def results(self):  # type: ignore[no-untyped-def]
            await asyncio.sleep(1)
            if False:
                yield FinalTranscript("unreachable", TranscriptLanguage("en"))

    class SlowProvider:
        name = "slow"

        async def readiness(self) -> bool:
            return True

        async def start(self, _request: TranscriptionRequest) -> SlowSession:
            return SlowSession()

    events: list[tuple[str, dict[str, object]]] = []

    async def publish(_job: object, event: str, payload: dict[str, object]) -> None:
        events.append((event, payload))

    registry = InMemoryTranscriptionJobs(SlowProvider(), publish, timeout_seconds=0.01)
    await registry.submit(request())
    await asyncio.sleep(0.02)

    assert events[-1] == ("transcript.error", {"code": "transcription_timeout"})
