"""M9D final-transcript dispatch contract tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tara_api.agent.service import AgentService
from tara_api.api.v1.websocket import submit_final_transcript
from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from tara_api.domain.transport import ConnectionContext, ConnectionState

from .conftest import ActiveSessions, MemoryAgentStore, service


class FakeConnection:
    def __init__(self, agent_service: AgentService, context: AuthenticatedOwnerContext) -> None:
        self.context = ConnectionContext(uuid4(), context.owner.id, context.session.id, 1, datetime.now(UTC))
        self.authenticated_context = context
        self.agent_service = agent_service
        self.state = ConnectionState.ACTIVE
        self.agent_tasks = set()
        self.events: list[tuple[str, dict[str, object]]] = []

    async def send_event(self, event_type: str, payload: dict[str, object], sequence: int | None = None) -> None:
        self.events.append((event_type, payload))


async def test_only_final_transcript_submission_starts_one_agent_request() -> None:
    now = datetime.now(UTC)
    owner = Owner(uuid4(), "owner@example.test", now)
    context = AuthenticatedOwnerContext(owner, OwnerSession(uuid4(), owner.id, now, now + timedelta(hours=1), now, None, None))
    sessions = ActiveSessions()
    sessions.active.add((owner.id, context.session.id))
    store = MemoryAgentStore()
    connection = FakeConnection(service(sessions, store, None), context)

    try:
        await asyncio.wait_for(submit_final_transcript(connection, "final speech", uuid4()), timeout=1)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert [event[0] for event in connection.events][:2] == ["agent.started", "agent.state"]
        assert len(store.accepted) == 1
    finally:
        await asyncio.wait_for(connection.agent_service.shutdown(), timeout=1)
