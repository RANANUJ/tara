"""Deterministic one-time confirmation workflow without model involvement."""

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from tara_api.domain.auth import AuthenticatedOwnerContext
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


class AuthenticatedContextValidator(Protocol):
    """Verify that an owner session remains valid at a safety boundary."""

    async def is_context_active(self, context: AuthenticatedOwnerContext) -> bool: ...


class DeterministicConfirmationService:
    """Bind exact tool requests to short-lived, one-time server-side authorization."""

    def __init__(
        self,
        store: SafetyStore,
        clock: Clock,
        ttl: timedelta = timedelta(minutes=2),
        context_validator: AuthenticatedContextValidator | None = None,
    ) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("confirmation ttl must be positive")
        self._store = store
        self._clock = clock
        self._ttl = ttl
        self._context_validator = context_validator

    async def create(self, request: ToolRequest, definition: ToolDefinition) -> PendingConfirmation:
        """M3-only unbound compatibility seam; it is not used by authenticated routes."""
        return await self._create(request, definition, None)

    async def create_authenticated(
        self,
        context: AuthenticatedOwnerContext,
        request: ToolRequest,
        definition: ToolDefinition,
    ) -> PendingConfirmation | None:
        if not await self._context_is_active(context):
            await self._publish_context_denial("confirmation.create.denied", context)
            return None
        return await self._create(request, definition, context)

    async def get_authenticated(
        self,
        context: AuthenticatedOwnerContext,
        confirmation_id: UUID,
    ) -> PendingConfirmation | None:
        if not await self._context_is_active(context):
            await self._publish_context_denial("confirmation.get.denied", context)
            return None
        confirmation = await self._store.get_confirmation(confirmation_id)
        if confirmation is None or not self._matches_context(confirmation, context):
            await self._publish_context_denial("confirmation.get.denied", context)
            return None
        return confirmation

    async def respond(self, confirmation_id: UUID, response: str) -> ConfirmationAuthorization | None:
        """M3-only unbound compatibility seam; it is not used by authenticated routes."""
        return await self._respond(confirmation_id, response, None)

    async def respond_authenticated(
        self,
        context: AuthenticatedOwnerContext,
        confirmation_id: UUID,
        response: str,
    ) -> ConfirmationAuthorization | None:
        if not await self._context_is_active(context):
            await self._publish_context_denial("confirmation.respond.denied", context)
            return None
        return await self._respond(confirmation_id, response, context)

    async def consume(self, authorization: ConfirmationAuthorization, request: ToolRequest) -> bool:
        """M3-only unbound compatibility seam; it is not used by authenticated routes."""
        return await self._consume(authorization, request, None)

    async def consume_authenticated(
        self,
        context: AuthenticatedOwnerContext,
        authorization: ConfirmationAuthorization,
        request: ToolRequest,
    ) -> bool:
        if not await self._context_is_active(context):
            await self._publish_context_denial("confirmation.consume.denied", context)
            return False
        if authorization.owner_id != context.owner.id or authorization.session_id != context.session.id:
            await self._publish_context_denial("confirmation.consume.denied", context)
            return False
        return await self._consume(authorization, request, context)

    async def _create(
        self,
        request: ToolRequest,
        definition: ToolDefinition,
        context: AuthenticatedOwnerContext | None,
    ) -> PendingConfirmation:
        now = self._clock.now()
        confirmation = PendingConfirmation(
            id=uuid4(),
            request_hash=request.canonical_hash(),
            tool_name=definition.name,
            prompt=self._prompt(definition, request),
            status=ConfirmationStatus.AWAITING_CONFIRMATION,
            expires_at=now + self._ttl,
            created_at=now,
            owner_id=context.owner.id if context else None,
            session_id=context.session.id if context else None,
        )
        await self._store.create_confirmation(
            confirmation,
            self._audit_event("confirmation.created", "awaiting_confirmation", confirmation, now),
        )
        return confirmation

    async def _respond(
        self,
        confirmation_id: UUID,
        response: str,
        context: AuthenticatedOwnerContext | None,
    ) -> ConfirmationAuthorization | None:
        confirmation = await self._store.get_confirmation(confirmation_id)
        if confirmation is None or not self._matches_context(confirmation, context):
            if context is not None:
                await self._publish_context_denial("confirmation.respond.denied", context)
            return None
        now = self._clock.now()
        if confirmation.expires_at <= now:
            await self._store.set_confirmation_status(
                confirmation_id, ConfirmationStatus.EXPIRED, now,
                self._audit_event("confirmation.expired", "expired", confirmation, now),
                **self._binding(context),
            )
            return None
        normalized_response = " ".join(response.strip().lower().split())
        if normalized_response in NEGATIVE_RESPONSES:
            await self._store.set_confirmation_status(
                confirmation_id, ConfirmationStatus.REJECTED, now,
                self._audit_event("confirmation.rejected", "rejected", confirmation, now),
                **self._binding(context),
            )
            return None
        if normalized_response not in AFFIRMATIVE_RESPONSES:
            return None
        approved = await self._store.set_confirmation_status(
            confirmation_id, ConfirmationStatus.APPROVED, now,
            self._audit_event("confirmation.approved", "approved", confirmation, now),
            **self._binding(context),
        )
        if approved is None:
            return None
        return ConfirmationAuthorization(
            approved.id, approved.request_hash, approved.expires_at, approved.owner_id, approved.session_id,
        )

    async def _consume(
        self,
        authorization: ConfirmationAuthorization,
        request: ToolRequest,
        context: AuthenticatedOwnerContext | None,
    ) -> bool:
        now = self._clock.now()
        confirmation = await self._store.get_confirmation(authorization.confirmation_id)
        if confirmation is None or not self._matches_context(confirmation, context):
            if context is not None:
                await self._publish_context_denial("confirmation.consume.denied", context)
            return False
        if authorization.expires_at <= now:
            await self._store.set_confirmation_status(
                authorization.confirmation_id, ConfirmationStatus.EXPIRED, now,
                self._audit_event("confirmation.expired", "expired", confirmation, now),
                **self._binding(context),
            )
            return False
        if authorization.request_hash != request.canonical_hash():
            await self._store.set_confirmation_status(
                authorization.confirmation_id, ConfirmationStatus.INVALIDATED, now,
                self._audit_event("confirmation.invalidated", "invalidated", confirmation, now),
                **self._binding(context),
            )
            return False
        if confirmation.status != ConfirmationStatus.APPROVED:
            return False
        return await self._store.consume_confirmation(
            authorization.confirmation_id, authorization.request_hash, now,
            self._audit_event("confirmation.consumed", "executing", confirmation, now),
            **self._binding(context),
        )

    async def _context_is_active(self, context: AuthenticatedOwnerContext) -> bool:
        return self._context_validator is not None and await self._context_validator.is_context_active(context)

    @staticmethod
    def _matches_context(confirmation: PendingConfirmation, context: AuthenticatedOwnerContext | None) -> bool:
        if context is None:
            return confirmation.owner_id is None and confirmation.session_id is None
        return confirmation.owner_id == context.owner.id and confirmation.session_id == context.session.id

    @staticmethod
    def _binding(context: AuthenticatedOwnerContext | None) -> dict[str, UUID | None]:
        return {} if context is None else {"owner_id": context.owner.id, "session_id": context.session.id}

    async def _publish_context_denial(self, event_type: str, context: AuthenticatedOwnerContext) -> None:
        await self._store.publish(
            AuditEvent(event_type, "denied", self._clock.now(), str(context.owner.id), {"session_id": str(context.session.id)})
        )

    @staticmethod
    def _prompt(definition: ToolDefinition, request: ToolRequest) -> str:
        safe_arguments = ", ".join(sorted(request.arguments)) or "no additional details"
        return f"Confirm {definition.summary_template} ({safe_arguments})?"

    @staticmethod
    def _audit_event(event_type: str, outcome: str, confirmation: PendingConfirmation, occurred_at: datetime) -> AuditEvent:
        return AuditEvent(
            event_type=event_type,
            outcome=outcome,
            occurred_at=occurred_at,
            subject_reference=str(confirmation.id),
            safe_metadata={"tool_name": confirmation.tool_name, "request_hash_prefix": confirmation.request_hash[:12]},
        )
