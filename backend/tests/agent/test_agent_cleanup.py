import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tara_api.agent.registry import AgentJob, AgentRequestRegistry
from tara_api.domain.agent import AgentInputSource, AgentRequest, AgentResponse, AgentState


async def test_terminal_records_are_bounded_and_shutdown_cancels_work() -> None:
    registry = AgentRequestRegistry(maximum_queued=2, maximum_concurrent=1, maximum_per_connection=1, maximum_per_session=2, maximum_per_owner=2, maximum_terminal_records=1, terminal_retention=timedelta(milliseconds=1))

    async def done(job: AgentJob) -> AgentResponse:
        return AgentResponse(job.request.request_id, "done", AgentState.COMPLETED, datetime.now(UTC))

    for key in ("one", "two"):
        request = AgentRequest(uuid4(), uuid4(), uuid4(), uuid4(), None, AgentInputSource.DIRECT_TEXT, "hello", datetime.now(UTC), uuid4(), None, key)
        await registry.submit(request, done)
    await asyncio.sleep(0.01)
    await registry.cleanup()

    assert (await registry.counts())[2] <= 1
    await registry.shutdown()
