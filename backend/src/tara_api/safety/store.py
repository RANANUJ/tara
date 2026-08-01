"""Persistence port used by confirmation and audit services."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from tara_api.domain.models import AuditEvent, ConfirmationStatus, PendingConfirmation


class SafetyStore(Protocol):
    """Store confirmation transitions and content-minimized audit events atomically."""

    async def create_confirmation(self, confirmation: PendingConfirmation, audit_event: AuditEvent) -> None: ...

    async def get_confirmation(self, confirmation_id: UUID) -> PendingConfirmation | None: ...

    async def set_confirmation_status(
        self,
        confirmation_id: UUID,
        status: ConfirmationStatus,
        occurred_at: datetime,
        audit_event: AuditEvent,
    ) -> PendingConfirmation | None: ...

    async def consume_confirmation(
        self,
        confirmation_id: UUID,
        request_hash: str,
        occurred_at: datetime,
        audit_event: AuditEvent,
    ) -> bool: ...
