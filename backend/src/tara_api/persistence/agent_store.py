"""M9C persistence adapter; ORM entities stay inside this module."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from tara_api.domain.agent import AgentError, AgentRequest, AgentResponse, AgentState, ModelUsage
from tara_api.persistence.database import Database
from tara_api.persistence.types import ConversationTurnRole, ConversationTurnStatus


class ConversationUnavailableError(RuntimeError):
    """Raise a safe service-level condition for an unknown or foreign conversation."""


class SqlAlchemyAgentPersistenceStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def resolve_conversation(self, owner_id: UUID, conversation_id: UUID | None) -> UUID:
        async with self._database.unit_of_work() as unit_of_work:
            if conversation_id is None:
                return (await unit_of_work.conversations.create(owner_id=owner_id)).id
            conversation = await unit_of_work.conversations.get_for_owner(conversation_id, owner_id)
            if conversation is None:
                raise ConversationUnavailableError
            return conversation.id

    async def record_accepted(self, request: AgentRequest) -> bool:
        if request.conversation_id is None or request.idempotency_key_hash is None:
            raise ValueError("agent request is missing persistence identity")
        try:
            async with self._database.unit_of_work() as unit_of_work:
                existing = await unit_of_work.agent_requests.get_by_idempotency(
                    request.owner_id, request.session_id, request.idempotency_key_hash
                )
                if existing is not None:
                    return False
                await unit_of_work.agent_requests.create(
                    request.request_id,
                    request.owner_id,
                    request.session_id,
                    request.conversation_id,
                    request.source.value,
                    request.idempotency_key_hash,
                    AgentState.QUEUED.value,
                    connection_id=request.connection_id,
                    source_transcript_id=request.source_transcript_id,
                )
        except IntegrityError:
            return False
        return True

    async def record_completed(
        self,
        request: AgentRequest,
        response: AgentResponse,
        *,
        provider_name: str | None,
        model_identifier: str | None,
        usage: ModelUsage | None,
        duration_ms: int | None,
    ) -> None:
        if request.conversation_id is None:
            raise ValueError("agent request has no conversation")
        usage_data = self._usage(usage)
        async with self._database.unit_of_work() as unit_of_work:
            existing = await unit_of_work.agent_requests.get_by_id(request.request_id)
            if existing is None:
                raise ValueError("agent request is unavailable")
            if existing.status == AgentState.COMPLETED.value:
                return
            turns = await unit_of_work.turns.list_for_conversation(request.conversation_id, limit=1000)
            sequence = max((turn.sequence for turn in turns), default=0) + 1
            await unit_of_work.turns.create(
                request.conversation_id,
                sequence,
                ConversationTurnRole.USER,
                ConversationTurnStatus.COMPLETED,
                request.text,
                agent_request_id=request.request_id,
                safe_metadata={"input_source": request.source.value},
            )
            await unit_of_work.turns.create(
                request.conversation_id,
                sequence + 1,
                ConversationTurnRole.ASSISTANT,
                ConversationTurnStatus.COMPLETED,
                response.text,
                agent_request_id=request.request_id,
                safe_metadata=self._assistant_metadata(provider_name, model_identifier, usage_data, duration_ms),
            )
            await unit_of_work.agent_requests.update_terminal(
                request.request_id,
                AgentState.COMPLETED.value,
                route_category=response.route.category.value if response.route else None,
                provider_name=provider_name,
                model_identifier=model_identifier,
                usage=usage_data,
                duration_ms=duration_ms,
            )

    async def record_terminal(self, request: AgentRequest, state: AgentState, error: AgentError | None) -> None:
        async with self._database.unit_of_work() as unit_of_work:
            await unit_of_work.agent_requests.update_terminal(
                request.request_id,
                state.value,
                failure_code=error.value if error else None,
            )

    @staticmethod
    def _usage(usage: ModelUsage | None) -> dict[str, int] | None:
        if usage is None:
            return None
        return {key: value for key, value in {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}.items() if value is not None}

    @staticmethod
    def _assistant_metadata(
        provider_name: str | None,
        model_identifier: str | None,
        usage: dict[str, int] | None,
        duration_ms: int | None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {}
        if provider_name is not None:
            metadata["provider_name"] = provider_name
        if model_identifier is not None:
            metadata["model_identifier"] = model_identifier
        if usage is not None:
            metadata["usage"] = usage
        if duration_ms is not None:
            metadata["duration_ms"] = duration_ms
        return metadata
