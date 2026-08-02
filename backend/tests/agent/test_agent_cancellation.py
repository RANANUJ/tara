import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from tara_api.agent.registry import AgentJob
from tara_api.domain.agent import AgentInputSource, AgentRequest, AgentResponse, AgentState

from .conftest import registry


async def test_active_cancellation_is_owner_session_connection_bound() -> None:
    owner_id, session_id, connection_id = uuid4(), uuid4(), uuid4()
    request = AgentRequest(uuid4(), uuid4(), owner_id, session_id, connection_id, AgentInputSource.DIRECT_TEXT, "hello", datetime.now(UTC), uuid4(), None, "cancel")
    items = registry()
    started = asyncio.Event()

    async def slow(job: AgentJob) -> AgentResponse:
        started.set()
        await asyncio.Event().wait()
        return AgentResponse(job.request.request_id, "late", AgentState.COMPLETED, datetime.now(UTC))

    pending = asyncio.create_task(items.submit(request, slow))
    await started.wait()
    assert await items.cancel(request.request_id, owner_id, session_id, uuid4()) is False
    assert await items.cancel(request.request_id, owner_id, session_id, connection_id) is True
    result = await pending

    assert result.state is AgentState.CANCELED
    assert await items.cancel(request.request_id, owner_id, session_id, connection_id) is True
    await items.shutdown()
