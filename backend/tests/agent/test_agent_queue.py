import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.agent.registry import AgentJob
from tara_api.domain.agent import AgentError, AgentInputSource, AgentRequest, AgentResponse, AgentState

from .conftest import registry


def request(key: str, *, owner_id=None, session_id=None, connection_id=None) -> AgentRequest:
    return AgentRequest(uuid4(), uuid4(), owner_id or uuid4(), session_id or uuid4(), connection_id, AgentInputSource.DIRECT_TEXT, "hello", datetime.now(UTC), uuid4(), None, key)


async def test_queue_respects_fifo_and_concurrency() -> None:
    items = registry(maximum_queued=3, maximum_concurrent=1)
    started: list[str] = []
    release = asyncio.Event()

    async def operation(job: AgentJob) -> AgentResponse:
        started.append(job.request.idempotency_key_hash or "")
        if len(started) == 1:
            await release.wait()
        return AgentResponse(job.request.request_id, "done", AgentState.COMPLETED, datetime.now(UTC))

    first = asyncio.create_task(items.submit(request("one"), operation))
    await asyncio.sleep(0)
    second = asyncio.create_task(items.submit(request("two"), operation))
    release.set()
    await asyncio.gather(first, second)

    assert started == ["one", "two"]
    assert await items.counts() == (0, 0, 2)
    await items.shutdown()


async def test_queue_and_identity_limits_are_typed() -> None:
    owner_id, session_id, connection_id = uuid4(), uuid4(), uuid4()
    items = registry(maximum_queued=2, maximum_per_connection=1)
    release = asyncio.Event()

    async def slow(job: AgentJob) -> AgentResponse:
        await release.wait()
        return AgentResponse(job.request.request_id, "done", AgentState.COMPLETED, datetime.now(UTC))

    task = asyncio.create_task(items.submit(request("one", owner_id=owner_id, session_id=session_id, connection_id=connection_id), slow))
    await asyncio.sleep(0)
    with pytest.raises(ValueError, match=AgentError.CONNECTION_REQUEST_LIMIT.value):
        await items.submit(request("two", owner_id=owner_id, session_id=session_id, connection_id=connection_id), slow)
    release.set()
    await task
    await items.shutdown()
