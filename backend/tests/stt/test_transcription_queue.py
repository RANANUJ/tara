from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs


def request(connection_id: object | None = None) -> TranscriptionRequest:
    return TranscriptionRequest(uuid4(), uuid4(), uuid4(), connection_id or uuid4(), uuid4(), uuid4(), b"\0\0" * 640, datetime.now(UTC))  # type: ignore[arg-type]


async def test_queue_and_connection_limits_reject_without_partial_registration() -> None:
    async def publish(*_args: object) -> None: pass
    registry = InMemoryTranscriptionJobs(FakeSpeechToTextProvider(), publish, maximum_queued=1, maximum_per_connection=1)
    first = request()
    await registry.submit(first)
    with pytest.raises(ValueError):
        await registry.submit(request())
