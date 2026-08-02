"""M9C SQLAlchemy repository for content-minimized agent request metadata."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tara_api.persistence.models import AgentRequestModel
from tara_api.persistence.repositories.sqlalchemy import _agent_request_record
from tara_api.persistence.types import AgentRequestRecord


class SqlAlchemyAgentRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        request_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        conversation_id: UUID,
        source: str,
        idempotency_key_hash: str,
        status: str,
        *,
        connection_id: UUID | None = None,
        source_transcript_id: UUID | None = None,
    ) -> AgentRequestRecord:
        model = AgentRequestModel(
            id=request_id,
            owner_id=owner_id,
            session_id=session_id,
            connection_id=connection_id,
            conversation_id=conversation_id,
            source=source,
            source_transcript_id=source_transcript_id,
            idempotency_key_hash=idempotency_key_hash,
            status=status,
        )
        self._session.add(model)
        await self._session.flush()
        return _agent_request_record(model)

    async def get_by_idempotency(
        self,
        owner_id: UUID,
        session_id: UUID,
        idempotency_key_hash: str,
    ) -> AgentRequestRecord | None:
        statement = select(AgentRequestModel).where(
            AgentRequestModel.owner_id == owner_id,
            AgentRequestModel.session_id == session_id,
            AgentRequestModel.idempotency_key_hash == idempotency_key_hash,
        )
        model = (await self._session.scalars(statement)).one_or_none()
        return _agent_request_record(model) if model else None

    async def get_by_id(self, request_id: UUID) -> AgentRequestRecord | None:
        model = await self._session.get(AgentRequestModel, request_id)
        return _agent_request_record(model) if model else None

    async def update_terminal(
        self,
        request_id: UUID,
        status: str,
        *,
        route_category: str | None = None,
        failure_code: str | None = None,
        provider_name: str | None = None,
        model_identifier: str | None = None,
        usage: dict[str, int] | None = None,
        duration_ms: int | None = None,
    ) -> AgentRequestRecord | None:
        model = await self._session.get(AgentRequestModel, request_id)
        if model is None:
            return None
        model.status = status
        model.route_category = route_category
        model.failure_code = failure_code
        model.provider_name = provider_name
        model.model_identifier = model_identifier
        model.usage = usage
        model.duration_ms = duration_ms
        await self._session.flush()
        return _agent_request_record(model)
