"""Concrete SQLAlchemy repositories for M2 foundational entities."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from tara_api.persistence.models import (
    AuditEventModel,
    ConfirmationConsumptionModel,
    ConversationModel,
    ConversationTurnModel,
    PendingConfirmationModel,
    PermissionSettingModel,
    SafeServiceConfigurationModel,
    SchedulerJobMetadataModel,
    StructuredMemoryModel,
)
from tara_api.persistence.types import (
    AuditEventRecord,
    ConfirmationAlreadyConsumedError,
    ConfirmationConsumptionRecord,
    ConfirmationDecision,
    ConfirmationExpiredError,
    ConfirmationStatus,
    ConversationRecord,
    ConversationTurnRecord,
    ConversationTurnRole,
    ConversationTurnStatus,
    MemoryCategory,
    MemorySource,
    PendingConfirmationRecord,
    PermissionGrantState,
    PermissionSettingRecord,
    RetentionCategory,
    SafeServiceConfigurationRecord,
    SchedulerJobMetadataRecord,
    SchedulerJobStatus,
    StructuredMemoryRecord,
    UnsafeConfigurationKeyError,
    ensure_utc,
    utc_now,
)

SENSITIVE_CONFIGURATION_KEY_PARTS = ("authorization", "cookie", "password", "secret", "token", "api_key")


def _validate_pagination(limit: int, offset: int) -> None:
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if offset < 0:
        raise ValueError("offset must be greater than or equal to zero")


def _contains_sensitive_configuration_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            not _is_safe_configuration_key(key) or _contains_sensitive_configuration_key(nested_value)
            for key, nested_value in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_configuration_key(item) for item in value)
    return False


def _is_safe_configuration_key(config_key: str) -> bool:
    normalized_key = config_key.lower()
    return not any(part in normalized_key for part in SENSITIVE_CONFIGURATION_KEY_PARTS)


def _conversation_record(model: ConversationModel) -> ConversationRecord:
    return ConversationRecord(model.id, model.label, model.created_at, model.updated_at)


def _turn_record(model: ConversationTurnModel) -> ConversationTurnRecord:
    return ConversationTurnRecord(
        model.id,
        model.conversation_id,
        model.sequence,
        model.role,
        model.status,
        model.content,
        model.created_at,
        model.updated_at,
    )


def _memory_record(model: StructuredMemoryModel) -> StructuredMemoryRecord:
    return StructuredMemoryRecord(
        model.id,
        model.category,
        model.content,
        model.source,
        model.source_reference,
        model.retention_category,
        model.pinned,
        model.expires_at,
        model.created_at,
        model.updated_at,
    )


def _permission_record(model: PermissionSettingModel) -> PermissionSettingRecord:
    return PermissionSettingRecord(
        model.id,
        model.capability,
        model.grant_state,
        dict(model.scope) if model.scope else None,
        model.created_at,
        model.updated_at,
    )


def _confirmation_record(model: PendingConfirmationModel) -> PendingConfirmationRecord:
    return PendingConfirmationRecord(
        model.id,
        model.conversation_id,
        model.permission_setting_id,
        model.action_type,
        model.action_summary,
        model.action_hash,
        model.status,
        model.expires_at,
        model.consumed_at,
        model.created_at,
        model.updated_at,
    )


def _consumption_record(model: ConfirmationConsumptionModel) -> ConfirmationConsumptionRecord:
    return ConfirmationConsumptionRecord(
        model.id,
        model.confirmation_id,
        model.decision,
        model.consumed_at,
        model.idempotency_key_hash,
        model.audit_summary,
    )


def _audit_event_record(model: AuditEventModel) -> AuditEventRecord:
    return AuditEventRecord(
        model.id,
        model.event_type,
        model.outcome,
        model.occurred_at,
        model.actor_reference,
        model.subject_reference,
        dict(model.safe_metadata) if model.safe_metadata else None,
    )


def _scheduler_job_record(model: SchedulerJobMetadataModel) -> SchedulerJobMetadataRecord:
    return SchedulerJobMetadataRecord(
        model.id,
        model.job_key,
        model.job_type,
        model.enabled,
        model.timezone,
        model.next_run_at,
        model.last_run_at,
        model.last_status,
        dict(model.safe_metadata) if model.safe_metadata else None,
        model.created_at,
        model.updated_at,
    )


def _configuration_record(model: SafeServiceConfigurationModel) -> SafeServiceConfigurationRecord:
    return SafeServiceConfigurationRecord(
        model.id,
        model.config_key,
        dict(model.value),
        model.created_at,
        model.updated_at,
    )


class SqlAlchemyConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, label: str | None = None) -> ConversationRecord:
        model = ConversationModel(label=label)
        self._session.add(model)
        await self._session.flush()
        return _conversation_record(model)

    async def get_by_id(self, conversation_id: UUID) -> ConversationRecord | None:
        model = await self._session.get(ConversationModel, conversation_id)
        return _conversation_record(model) if model else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[ConversationRecord]:
        _validate_pagination(limit, offset)
        statement = select(ConversationModel).order_by(ConversationModel.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(statement)
        return [_conversation_record(model) for model in result]

    async def update_label(self, conversation_id: UUID, label: str | None) -> ConversationRecord | None:
        model = await self._session.get(ConversationModel, conversation_id)
        if model is None:
            return None
        model.label = label
        await self._session.flush()
        return _conversation_record(model)

    async def delete(self, conversation_id: UUID) -> bool:
        result = await self._session.execute(delete(ConversationModel).where(ConversationModel.id == conversation_id))
        return cast(CursorResult[object], result).rowcount > 0


class SqlAlchemyConversationTurnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        conversation_id: UUID,
        sequence: int,
        role: ConversationTurnRole,
        status: ConversationTurnStatus,
        content: str,
    ) -> ConversationTurnRecord:
        model = ConversationTurnModel(
            conversation_id=conversation_id,
            sequence=sequence,
            role=role,
            status=status,
            content=content,
        )
        self._session.add(model)
        await self._session.flush()
        return _turn_record(model)

    async def get_by_id(self, turn_id: UUID) -> ConversationTurnRecord | None:
        model = await self._session.get(ConversationTurnModel, turn_id)
        return _turn_record(model) if model else None

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationTurnRecord]:
        _validate_pagination(limit, offset)
        statement = (
            select(ConversationTurnModel)
            .where(ConversationTurnModel.conversation_id == conversation_id)
            .order_by(ConversationTurnModel.sequence)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(statement)
        return [_turn_record(model) for model in result]

    async def update_status(
        self,
        turn_id: UUID,
        status: ConversationTurnStatus,
    ) -> ConversationTurnRecord | None:
        model = await self._session.get(ConversationTurnModel, turn_id)
        if model is None:
            return None
        model.status = status
        await self._session.flush()
        return _turn_record(model)

    async def delete(self, turn_id: UUID) -> bool:
        result = await self._session.execute(delete(ConversationTurnModel).where(ConversationTurnModel.id == turn_id))
        return cast(CursorResult[object], result).rowcount > 0


class SqlAlchemyStructuredMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        category: MemoryCategory,
        content: str,
        source: MemorySource,
        retention_category: RetentionCategory,
        *,
        source_reference: str | None = None,
        pinned: bool = False,
        expires_at: datetime | None = None,
    ) -> StructuredMemoryRecord:
        model = StructuredMemoryModel(
            category=category,
            content=content,
            source=source,
            source_reference=source_reference,
            retention_category=retention_category,
            pinned=pinned,
            expires_at=ensure_utc(expires_at) if expires_at else None,
        )
        self._session.add(model)
        await self._session.flush()
        return _memory_record(model)

    async def get_by_id(self, memory_id: UUID) -> StructuredMemoryRecord | None:
        model = await self._session.get(StructuredMemoryModel, memory_id)
        return _memory_record(model) if model else None

    async def list_memories(
        self,
        limit: int = 50,
        offset: int = 0,
        category: MemoryCategory | None = None,
    ) -> list[StructuredMemoryRecord]:
        _validate_pagination(limit, offset)
        statement = select(StructuredMemoryModel)
        if category is not None:
            statement = statement.where(StructuredMemoryModel.category == category)
        statement = statement.order_by(StructuredMemoryModel.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(statement)
        return [_memory_record(model) for model in result]

    async def update(
        self,
        memory_id: UUID,
        *,
        content: str | None = None,
        pinned: bool | None = None,
    ) -> StructuredMemoryRecord | None:
        model = await self._session.get(StructuredMemoryModel, memory_id)
        if model is None:
            return None
        if content is not None:
            model.content = content
        if pinned is not None:
            model.pinned = pinned
        await self._session.flush()
        return _memory_record(model)

    async def hard_delete(self, memory_id: UUID) -> bool:
        result = await self._session.execute(delete(StructuredMemoryModel).where(StructuredMemoryModel.id == memory_id))
        return cast(CursorResult[object], result).rowcount > 0

    async def list_for_export(self, limit: int = 100, offset: int = 0) -> list[StructuredMemoryRecord]:
        return await self.list_memories(limit=limit, offset=offset)

    async def list_for_retention_cleanup(
        self,
        now: datetime,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StructuredMemoryRecord]:
        _validate_pagination(limit, offset)
        statement = (
            select(StructuredMemoryModel)
            .where(
                StructuredMemoryModel.retention_category.in_(
                    (RetentionCategory.TASK, RetentionCategory.CASUAL)
                ),
                StructuredMemoryModel.pinned.is_(False),
                StructuredMemoryModel.expires_at.is_not(None),
                StructuredMemoryModel.expires_at <= ensure_utc(now),
            )
            .order_by(StructuredMemoryModel.expires_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(statement)
        return [_memory_record(model) for model in result]


class SqlAlchemyPermissionSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        capability: str,
        grant_state: PermissionGrantState = PermissionGrantState.DISABLED,
        scope: dict[str, object] | None = None,
    ) -> PermissionSettingRecord:
        model = PermissionSettingModel(capability=capability, grant_state=grant_state, scope=scope)
        self._session.add(model)
        await self._session.flush()
        return _permission_record(model)

    async def get_by_id(self, setting_id: UUID) -> PermissionSettingRecord | None:
        model = await self._session.get(PermissionSettingModel, setting_id)
        return _permission_record(model) if model else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[PermissionSettingRecord]:
        _validate_pagination(limit, offset)
        statement = select(PermissionSettingModel).order_by(PermissionSettingModel.capability).offset(offset).limit(limit)
        result = await self._session.scalars(statement)
        return [_permission_record(model) for model in result]

    async def set_grant_state(
        self,
        setting_id: UUID,
        grant_state: PermissionGrantState,
    ) -> PermissionSettingRecord | None:
        model = await self._session.get(PermissionSettingModel, setting_id)
        if model is None:
            return None
        model.grant_state = grant_state
        await self._session.flush()
        return _permission_record(model)

    async def delete(self, setting_id: UUID) -> bool:
        result = await self._session.execute(delete(PermissionSettingModel).where(PermissionSettingModel.id == setting_id))
        return cast(CursorResult[object], result).rowcount > 0


class SqlAlchemyConfirmationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        action_type: str,
        action_summary: str,
        action_hash: str,
        expires_at: datetime,
        *,
        conversation_id: UUID | None = None,
        permission_setting_id: UUID | None = None,
    ) -> PendingConfirmationRecord:
        model = PendingConfirmationModel(
            conversation_id=conversation_id,
            permission_setting_id=permission_setting_id,
            action_type=action_type,
            action_summary=action_summary,
            action_hash=action_hash,
            status=ConfirmationStatus.AWAITING_CONFIRMATION,
            expires_at=ensure_utc(expires_at),
        )
        self._session.add(model)
        await self._session.flush()
        return _confirmation_record(model)

    async def get_by_id(self, confirmation_id: UUID) -> PendingConfirmationRecord | None:
        model = await self._session.get(PendingConfirmationModel, confirmation_id)
        return _confirmation_record(model) if model else None

    async def list_pending(self, limit: int = 50, offset: int = 0) -> list[PendingConfirmationRecord]:
        _validate_pagination(limit, offset)
        statement = (
            select(PendingConfirmationModel)
            .where(PendingConfirmationModel.status == ConfirmationStatus.AWAITING_CONFIRMATION)
            .order_by(PendingConfirmationModel.expires_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(statement)
        return [_confirmation_record(model) for model in result]

    async def consume(
        self,
        confirmation_id: UUID,
        decision: ConfirmationDecision,
        *,
        idempotency_key_hash: str | None = None,
        audit_summary: str | None = None,
        consumed_at: datetime | None = None,
    ) -> ConfirmationConsumptionRecord:
        consumed_at_utc = ensure_utc(consumed_at) if consumed_at else utc_now()
        statement = (
            update(PendingConfirmationModel)
            .where(
                PendingConfirmationModel.id == confirmation_id,
                PendingConfirmationModel.status == ConfirmationStatus.AWAITING_CONFIRMATION,
                PendingConfirmationModel.consumed_at.is_(None),
                PendingConfirmationModel.expires_at > consumed_at_utc,
            )
            .values(
                status=(
                    ConfirmationStatus.APPROVED
                    if decision == ConfirmationDecision.APPROVED
                    else ConfirmationStatus.REJECTED
                ),
                consumed_at=consumed_at_utc,
            )
            .returning(PendingConfirmationModel)
        )
        result = await self._session.execute(statement)
        confirmation = result.scalar_one_or_none()
        if confirmation is None:
            existing = await self._session.get(PendingConfirmationModel, confirmation_id)
            if existing is not None and existing.expires_at <= consumed_at_utc:
                raise ConfirmationExpiredError("confirmation has expired")
            raise ConfirmationAlreadyConsumedError("confirmation is not eligible for consumption")

        consumption = ConfirmationConsumptionModel(
            confirmation_id=confirmation.id,
            decision=decision,
            consumed_at=consumed_at_utc,
            idempotency_key_hash=idempotency_key_hash,
            audit_summary=audit_summary,
        )
        self._session.add(consumption)
        await self._session.flush()
        return _consumption_record(consumption)

    async def delete(self, confirmation_id: UUID) -> bool:
        result = await self._session.execute(delete(PendingConfirmationModel).where(PendingConfirmationModel.id == confirmation_id))
        return cast(CursorResult[object], result).rowcount > 0


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        event_type: str,
        outcome: str,
        *,
        actor_reference: str | None = None,
        subject_reference: str | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        model = AuditEventModel(
            event_type=event_type,
            outcome=outcome,
            actor_reference=actor_reference,
            subject_reference=subject_reference,
            safe_metadata=safe_metadata,
        )
        self._session.add(model)
        await self._session.flush()
        return _audit_event_record(model)

    async def list(self, limit: int = 50, offset: int = 0) -> list[AuditEventRecord]:
        _validate_pagination(limit, offset)
        statement = select(AuditEventModel).order_by(AuditEventModel.occurred_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(statement)
        return [_audit_event_record(model) for model in result]


class SqlAlchemySchedulerJobMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        job_key: str,
        job_type: str,
        timezone: str,
        *,
        enabled: bool = True,
        next_run_at: datetime | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> SchedulerJobMetadataRecord:
        model = SchedulerJobMetadataModel(
            job_key=job_key,
            job_type=job_type,
            enabled=enabled,
            timezone=timezone,
            next_run_at=ensure_utc(next_run_at) if next_run_at else None,
            safe_metadata=safe_metadata,
        )
        self._session.add(model)
        await self._session.flush()
        return _scheduler_job_record(model)

    async def get_by_id(self, job_id: UUID) -> SchedulerJobMetadataRecord | None:
        model = await self._session.get(SchedulerJobMetadataModel, job_id)
        return _scheduler_job_record(model) if model else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[SchedulerJobMetadataRecord]:
        _validate_pagination(limit, offset)
        statement = select(SchedulerJobMetadataModel).order_by(SchedulerJobMetadataModel.job_key).offset(offset).limit(limit)
        result = await self._session.scalars(statement)
        return [_scheduler_job_record(model) for model in result]

    async def update_enabled(
        self,
        job_id: UUID,
        enabled: bool,
        status: SchedulerJobStatus | None = None,
    ) -> SchedulerJobMetadataRecord | None:
        model = await self._session.get(SchedulerJobMetadataModel, job_id)
        if model is None:
            return None
        model.enabled = enabled
        model.last_status = status or (SchedulerJobStatus.SCHEDULED if enabled else SchedulerJobStatus.DISABLED)
        await self._session.flush()
        return _scheduler_job_record(model)

    async def delete(self, job_id: UUID) -> bool:
        result = await self._session.execute(delete(SchedulerJobMetadataModel).where(SchedulerJobMetadataModel.id == job_id))
        return cast(CursorResult[object], result).rowcount > 0


class SqlAlchemySafeServiceConfigurationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        config_key: str,
        value: dict[str, object],
    ) -> SafeServiceConfigurationRecord:
        if not _is_safe_configuration_key(config_key) or _contains_sensitive_configuration_key(value):
            raise UnsafeConfigurationKeyError("secret configuration values must not be persisted")
        statement = select(SafeServiceConfigurationModel).where(
            SafeServiceConfigurationModel.config_key == config_key
        )
        model = (await self._session.scalars(statement)).one_or_none()
        if model is None:
            model = SafeServiceConfigurationModel(config_key=config_key, value=value)
            self._session.add(model)
        else:
            model.value = value
        await self._session.flush()
        return _configuration_record(model)

    async def get_by_key(self, config_key: str) -> SafeServiceConfigurationRecord | None:
        statement = select(SafeServiceConfigurationModel).where(
            SafeServiceConfigurationModel.config_key == config_key
        )
        model = (await self._session.scalars(statement)).one_or_none()
        return _configuration_record(model) if model else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[SafeServiceConfigurationRecord]:
        _validate_pagination(limit, offset)
        statement = select(SafeServiceConfigurationModel).order_by(
            SafeServiceConfigurationModel.config_key
        ).offset(offset).limit(limit)
        result = await self._session.scalars(statement)
        return [_configuration_record(model) for model in result]

    async def delete(self, config_key: str) -> bool:
        result = await self._session.execute(
            delete(SafeServiceConfigurationModel).where(
                SafeServiceConfigurationModel.config_key == config_key
            )
        )
        return cast(CursorResult[object], result).rowcount > 0
