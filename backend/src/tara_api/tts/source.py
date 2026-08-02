"""Bounded one-time bridge from completed agent responses to TTS."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from uuid import UUID

from tara_api.domain.agent import AgentRequest, AgentResponse, AgentState
from tara_api.domain.tts import ApprovedAgentResponse


class InMemoryApprovedAgentResponseSource:
    """Short-lived server-only responses; text is released when TTS resolves it."""

    def __init__(self, maximum_records: int = 64) -> None:
        if maximum_records < 1:
            raise ValueError("approved response source must be bounded")
        self._maximum_records = maximum_records
        self._responses: OrderedDict[UUID, ApprovedAgentResponse] = OrderedDict()
        self._lock = asyncio.Lock()

    async def register(self, request: AgentRequest, response: AgentResponse) -> bool:
        if response.state is not AgentState.COMPLETED or response.error is not None or request.conversation_id is None:
            return False
        approved = ApprovedAgentResponse(
            request.request_id,
            request.owner_id,
            request.session_id,
            request.connection_id,
            request.conversation_id,
            response.text,
            response.created_at,
        )
        async with self._lock:
            if request.request_id in self._responses:
                return False
            self._responses[request.request_id] = approved
            while len(self._responses) > self._maximum_records:
                self._responses.popitem(last=False)
        return True

    async def discard(self, agent_request_id: UUID) -> None:
        async with self._lock:
            self._responses.pop(agent_request_id, None)

    async def resolve_completed_response(
        self,
        *,
        owner_id: UUID,
        session_id: UUID,
        connection_id: UUID | None,
        agent_request_id: UUID,
        assistant_turn_id: UUID | None,
    ) -> ApprovedAgentResponse | None:
        async with self._lock:
            response = self._responses.get(agent_request_id)
            if response is None or response.assistant_turn_id != assistant_turn_id:
                return None
            if (response.owner_id, response.session_id, response.connection_id) != (owner_id, session_id, connection_id):
                return None
            return self._responses.pop(agent_request_id)
