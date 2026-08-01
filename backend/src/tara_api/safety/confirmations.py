"""Deterministic one-time confirmation workflow without model involvement."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from tara_api.domain.models import (
    AuditEvent,
    ConfirmationAuthorization,
    ConfirmationStatus,
    PendingConfirmation,
    ToolDefinition,
    ToolRequest,
)
from tara_api.domain.protocols import Clock
from tara_api.safety.store import SafetyStore

AFFIRMATIVE_RESPONSES = frozenset({"yes", "approve", "confirm", "i approve"})
NEGATIVE_RESPONSES = frozenset({"no", "reject", "cancel", "do not approve"})


class DeterministicConfirmationService:
    """Bind exact tool requests to short-lived, one-time server-side authorization."""

    def __init__(self, store: SafetyStore, clock: Clock, ttl: timedelta = timedelta(minutes=2)) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("confirmation ttl must be positive")
        self._store = store
        self._clock = clock
        self._ttl = ttl

    async def create(self, request: ToolRequest, definition: ToolDefinition) -> PendingConfirmation:
        now = self._clock.now()
        confirmation = PendingConfirmation(
            id=uuid4(),
            request_hash=request.canonical_hash(),
            tool_name=definition.name,
            prompt=self._prompt(definition, request),
            status=ConfirmationStatus.AWAITING_CONFIRMATION,
            expires_at=now + self._ttl,
            created_at=now,
        )
        await self._store.create_confirmation(
            confirmation,
            self._audit_event("confirmation.created", "awaiting_confirmation", confirmation, now),
        )
        return confirmation

    async def respond(self, confirmation_id: UUID, response: str) -> ConfirmationAuthorization | None:
        confirmation = await self._store.get_confirmation(confirmation_id)
        if confirmation is None:
            return None
        now = self._clock.now()
        if confirmation.expires_at <= now:
            await self._store.set_confirmation_status(
                confirmation_id,
                ConfirmationStatus.EXPIRED,
                now,
                self._audit_event("confirmation.expired", "expired", confirmation, now),
            )
            return None
        normalized_response = " ".join(response.strip().lower().split())
        if normalized_response in NEGATIVE_RESPONSES:
            await self._store.set_confirmation_status(
                confirmation_id,
                ConfirmationStatus.REJECTED,
                now,
                self._audit_event("confirmation.rejected", "rejected", confirmation, now),
            )
            return None
        if normalized_response not in AFFIRMATIVE_RESPONSES:
            return None
        approved = await self._store.set_confirmation_status(
            confirmation_id,
            ConfirmationStatus.APPROVED,
            now,
            self._audit_event("confirmation.approved", "approved", confirmation, now),
        )
        if approved is None:
            return None
        return ConfirmationAuthorization(approved.id, approved.request_hash, approved.expires_at)

    async def consume(self, authorization: ConfirmationAuthorization, request: ToolRequest) -> bool:
        now = self._clock.now()
        if authorization.expires_at <= now:
            confirmation = await self._store.get_confirmation(authorization.confirmation_id)
            if confirmation is not None:
                await self._store.set_confirmation_status(
                    authorization.confirmation_id,
                    ConfirmationStatus.EXPIRED,
                    now,
                    self._audit_event("confirmation.expired", "expired", confirmation, now),
                )
            return False
        if authorization.request_hash != request.canonical_hash():
            confirmation = await self._store.get_confirmation(authorization.confirmation_id)
            if confirmation is not None:
                await self._store.set_confirmation_status(
                    authorization.confirmation_id,
                    ConfirmationStatus.INVALIDATED,
                    now,
                    self._audit_event("confirmation.invalidated", "invalidated", confirmation, now),
                )
            return False
        confirmation = await self._store.get_confirmation(authorization.confirmation_id)
        if confirmation is None or confirmation.status != ConfirmationStatus.APPROVED:
            return False
        return await self._store.consume_confirmation(
            authorization.confirmation_id,
            authorization.request_hash,
            now,
            self._audit_event("confirmation.consumed", "executing", confirmation, now),
        )

    @staticmethod
    def _prompt(definition: ToolDefinition, request: ToolRequest) -> str:
        safe_arguments = ", ".join(sorted(request.arguments)) or "no additional details"
        return f"Confirm {definition.summary_template} ({safe_arguments})?"

    @staticmethod
    def _audit_event(
        event_type: str,
        outcome: str,
        confirmation: PendingConfirmation,
        occurred_at: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            event_type=event_type,
            outcome=outcome,
            occurred_at=occurred_at,
            subject_reference=str(confirmation.id),
            safe_metadata={"tool_name": confirmation.tool_name, "request_hash_prefix": confirmation.request_hash[:12]},
        )
