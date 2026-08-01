"""SQLAlchemy adapter for framework-independent safety confirmation contracts."""

from datetime import datetime
from uuid import UUID

from tara_api.domain.models import AuditEvent, ConfirmationStatus, PendingConfirmation
from tara_api.persistence.database import Database
from tara_api.persistence.repositories.sqlalchemy import SqlAlchemyAuditEventRepository
from tara_api.persistence.types import ConfirmationStatus as PersistenceConfirmationStatus
from tara_api.persistence.types import PendingConfirmationRecord


class SqlAlchemySafetyStore:
    """Persist safety transitions and audits without exposing ORM entities."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def publish(self, event: AuditEvent) -> None:
        async with self._database.unit_of_work() as unit_of_work:
            await self._publish_in_transaction(unit_of_work.audit_events, event)

    async def create_confirmation(self, confirmation: PendingConfirmation, audit_event: AuditEvent) -> None:
        async with self._database.unit_of_work() as unit_of_work:
            await unit_of_work.confirmations.create(
                confirmation.tool_name,
                confirmation.prompt,
                confirmation.request_hash,
                confirmation.expires_at,
                confirmation_id=confirmation.id,
                owner_id=confirmation.owner_id,
                owner_session_id=confirmation.session_id,
            )
            await self._publish_in_transaction(unit_of_work.audit_events, audit_event)

    async def get_confirmation(self, confirmation_id: UUID) -> PendingConfirmation | None:
        async with self._database.unit_of_work() as unit_of_work:
            record = await unit_of_work.confirmations.get_by_id(confirmation_id)
        return self._to_domain(record) if record else None

    async def set_confirmation_status(
        self,
        confirmation_id: UUID,
        status: ConfirmationStatus,
        occurred_at: datetime,
        audit_event: AuditEvent,
        *,
        owner_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> PendingConfirmation | None:
        async with self._database.unit_of_work() as unit_of_work:
            record = await unit_of_work.confirmations.transition(
                confirmation_id,
                PersistenceConfirmationStatus(status.value),
                occurred_at,
                owner_id=owner_id,
                owner_session_id=session_id,
            )
            if record is not None:
                await self._publish_in_transaction(unit_of_work.audit_events, audit_event)
        return self._to_domain(record) if record else None

    async def consume_confirmation(
        self,
        confirmation_id: UUID,
        request_hash: str,
        occurred_at: datetime,
        audit_event: AuditEvent,
        *,
        owner_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> bool:
        async with self._database.unit_of_work() as unit_of_work:
            record = await unit_of_work.confirmations.consume_approved(
                confirmation_id,
                request_hash,
                occurred_at,
                owner_id=owner_id,
                owner_session_id=session_id,
            )
            if record is None:
                return False
            await self._publish_in_transaction(unit_of_work.audit_events, audit_event)
        return True

    @staticmethod
    async def _publish_in_transaction(repository: SqlAlchemyAuditEventRepository, event: AuditEvent) -> None:
        await repository.create(
            event.event_type,
            event.outcome,
            subject_reference=event.subject_reference,
            safe_metadata=dict(event.safe_metadata),
        )

    @staticmethod
    def _to_domain(record: PendingConfirmationRecord) -> PendingConfirmation:
        return PendingConfirmation(
            id=record.id,
            request_hash=record.action_hash,
            tool_name=record.action_type,
            prompt=record.action_summary,
            status=ConfirmationStatus(record.status.value),
            expires_at=record.expires_at,
            created_at=record.created_at,
            owner_id=record.owner_id,
            session_id=record.owner_session_id,
        )
