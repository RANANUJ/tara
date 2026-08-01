"""Typed repository interfaces that return records, never ORM entities."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from tara_api.persistence.types import (
    AuditEventRecord,
    ConfirmationConsumptionRecord,
    ConfirmationDecision,
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
)


class ConversationRepository(Protocol):
    async def create(self, label: str | None = None) -> ConversationRecord: ...

    async def get_by_id(self, conversation_id: UUID) -> ConversationRecord | None: ...

    async def list(self, limit: int = 50, offset: int = 0) -> list[ConversationRecord]: ...

    async def update_label(self, conversation_id: UUID, label: str | None) -> ConversationRecord | None: ...

    async def delete(self, conversation_id: UUID) -> bool: ...


class ConversationTurnRepository(Protocol):
    async def create(
        self,
        conversation_id: UUID,
        sequence: int,
        role: ConversationTurnRole,
        status: ConversationTurnStatus,
        content: str,
    ) -> ConversationTurnRecord: ...

    async def get_by_id(self, turn_id: UUID) -> ConversationTurnRecord | None: ...

    async def list_for_conversation(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationTurnRecord]: ...

    async def update_status(
        self,
        turn_id: UUID,
        status: ConversationTurnStatus,
    ) -> ConversationTurnRecord | None: ...

    async def delete(self, turn_id: UUID) -> bool: ...


class StructuredMemoryRepository(Protocol):
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
    ) -> StructuredMemoryRecord: ...

    async def get_by_id(self, memory_id: UUID) -> StructuredMemoryRecord | None: ...

    async def list_memories(
        self,
        limit: int = 50,
        offset: int = 0,
        category: MemoryCategory | None = None,
    ) -> list[StructuredMemoryRecord]: ...

    async def update(
        self,
        memory_id: UUID,
        *,
        content: str | None = None,
        pinned: bool | None = None,
    ) -> StructuredMemoryRecord | None: ...

    async def hard_delete(self, memory_id: UUID) -> bool: ...

    async def list_for_export(self, limit: int = 100, offset: int = 0) -> list[StructuredMemoryRecord]: ...

    async def list_for_retention_cleanup(
        self,
        now: datetime,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StructuredMemoryRecord]: ...


class PermissionSettingRepository(Protocol):
    async def create(
        self,
        capability: str,
        grant_state: PermissionGrantState = PermissionGrantState.DISABLED,
        scope: dict[str, object] | None = None,
    ) -> PermissionSettingRecord: ...

    async def get_by_id(self, setting_id: UUID) -> PermissionSettingRecord | None: ...

    async def list(self, limit: int = 50, offset: int = 0) -> list[PermissionSettingRecord]: ...

    async def set_grant_state(
        self,
        setting_id: UUID,
        grant_state: PermissionGrantState,
    ) -> PermissionSettingRecord | None: ...

    async def delete(self, setting_id: UUID) -> bool: ...


class ConfirmationRepository(Protocol):
    async def create(
        self,
        action_type: str,
        action_summary: str,
        action_hash: str,
        expires_at: datetime,
        *,
        conversation_id: UUID | None = None,
        permission_setting_id: UUID | None = None,
    ) -> PendingConfirmationRecord: ...

    async def get_by_id(self, confirmation_id: UUID) -> PendingConfirmationRecord | None: ...

    async def list_pending(self, limit: int = 50, offset: int = 0) -> list[PendingConfirmationRecord]: ...

    async def consume(
        self,
        confirmation_id: UUID,
        decision: ConfirmationDecision,
        *,
        idempotency_key_hash: str | None = None,
        audit_summary: str | None = None,
        consumed_at: datetime | None = None,
    ) -> ConfirmationConsumptionRecord: ...

    async def delete(self, confirmation_id: UUID) -> bool: ...


class AuditEventRepository(Protocol):
    async def create(
        self,
        event_type: str,
        outcome: str,
        *,
        actor_reference: str | None = None,
        subject_reference: str | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> AuditEventRecord: ...

    async def list(self, limit: int = 50, offset: int = 0) -> list[AuditEventRecord]: ...


class SchedulerJobMetadataRepository(Protocol):
    async def create(
        self,
        job_key: str,
        job_type: str,
        timezone: str,
        *,
        enabled: bool = True,
        next_run_at: datetime | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> SchedulerJobMetadataRecord: ...

    async def get_by_id(self, job_id: UUID) -> SchedulerJobMetadataRecord | None: ...

    async def list(self, limit: int = 50, offset: int = 0) -> list[SchedulerJobMetadataRecord]: ...

    async def update_enabled(
        self,
        job_id: UUID,
        enabled: bool,
        status: SchedulerJobStatus | None = None,
    ) -> SchedulerJobMetadataRecord | None: ...

    async def delete(self, job_id: UUID) -> bool: ...


class SafeServiceConfigurationRepository(Protocol):
    async def upsert(
        self,
        config_key: str,
        value: dict[str, object],
    ) -> SafeServiceConfigurationRecord: ...

    async def get_by_key(self, config_key: str) -> SafeServiceConfigurationRecord | None: ...

    async def list(self, limit: int = 50, offset: int = 0) -> list[SafeServiceConfigurationRecord]: ...

    async def delete(self, config_key: str) -> bool: ...
