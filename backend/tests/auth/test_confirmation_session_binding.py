"""M4 confirmation ownership and session-binding tests."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from tara_api.domain.models import (
    ActionRiskLevel,
    AuditEvent,
    ConfirmationStatus,
    PendingConfirmation,
    PermissionScope,
    ToolDefinition,
    ToolRequest,
)
from tara_api.safety.confirmations import DeterministicConfirmationService


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


class ActiveContexts:
    def __init__(self, active: set[tuple[UUID, UUID]]) -> None:
        self.active = active

    async def is_context_active(self, context: AuthenticatedOwnerContext) -> bool:
        return (context.owner.id, context.session.id) in self.active


class MemoryStore:
    def __init__(self) -> None:
        self.confirmations: dict[UUID, PendingConfirmation] = {}
        self.audits: list[AuditEvent] = []

    async def publish(self, event: AuditEvent) -> None:
        self.audits.append(event)

    async def create_confirmation(self, confirmation: PendingConfirmation, audit_event: AuditEvent) -> None:
        self.confirmations[confirmation.id] = confirmation
        self.audits.append(audit_event)

    async def get_confirmation(self, confirmation_id: UUID) -> PendingConfirmation | None:
        return self.confirmations.get(confirmation_id)

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
        confirmation = self.confirmations.get(confirmation_id)
        if confirmation is None or (owner_id is not None and (confirmation.owner_id, confirmation.session_id) != (owner_id, session_id)):
            return None
        if confirmation.status not in {ConfirmationStatus.AWAITING_CONFIRMATION, ConfirmationStatus.APPROVED}:
            return None
        if status == ConfirmationStatus.APPROVED and confirmation.status != ConfirmationStatus.AWAITING_CONFIRMATION:
            return None
        updated = replace(confirmation, status=status)
        self.confirmations[confirmation_id] = updated
        self.audits.append(audit_event)
        return updated

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
        confirmation = self.confirmations.get(confirmation_id)
        if (
            confirmation is None
            or confirmation.status != ConfirmationStatus.APPROVED
            or confirmation.request_hash != request_hash
            or confirmation.expires_at <= occurred_at
            or (owner_id is not None and (confirmation.owner_id, confirmation.session_id) != (owner_id, session_id))
        ):
            return False
        self.confirmations[confirmation_id] = replace(confirmation, status=ConfirmationStatus.EXECUTING)
        self.audits.append(audit_event)
        return True


def context(owner_id: UUID | None = None, session_id: UUID | None = None) -> AuthenticatedOwnerContext:
    owner = Owner(owner_id or uuid4(), "owner@example.test", datetime(2026, 8, 1, tzinfo=UTC))
    session = OwnerSession(
        session_id or uuid4(), owner.id, datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 8, 2, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC), None, None,
    )
    return AuthenticatedOwnerContext(owner, session)


def definition() -> ToolDefinition:
    return ToolDefinition("message.send", "1", PermissionScope("messages.send"), ActionRiskLevel.OUTWARD_FACING, "send a message")


def request(target: str = "alice") -> ToolRequest:
    return ToolRequest("message.send", "1", {"target": target, "content": "private payload"})


async def test_authenticated_confirmation_binds_owner_and_session_and_consumes_once() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    owner_context = context()
    store = MemoryStore()
    service = DeterministicConfirmationService(store, clock, context_validator=ActiveContexts({(owner_context.owner.id, owner_context.session.id)}))

    pending = await service.create_authenticated(owner_context, request(), definition())
    assert pending is not None
    assert (pending.owner_id, pending.session_id) == (owner_context.owner.id, owner_context.session.id)
    assert "token" not in repr(pending).lower()

    authorization = await service.respond_authenticated(owner_context, pending.id, "yes")
    assert authorization is not None
    assert await service.consume_authenticated(owner_context, authorization, request()) is True
    assert await service.consume_authenticated(owner_context, authorization, request()) is False


async def test_cross_session_and_modified_or_expired_confirmations_are_denied() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    first = context()
    second = context(first.owner.id)
    store = MemoryStore()
    active = ActiveContexts({(first.owner.id, first.session.id), (second.owner.id, second.session.id)})
    service = DeterministicConfirmationService(store, clock, ttl=timedelta(seconds=1), context_validator=active)

    pending = await service.create_authenticated(first, request(), definition())
    assert pending is not None
    assert await service.respond_authenticated(second, pending.id, "yes") is None
    authorization = await service.respond_authenticated(first, pending.id, "yes")
    assert authorization is not None
    assert await service.consume_authenticated(second, authorization, request()) is False
    assert await service.consume_authenticated(first, authorization, request("bob")) is False

    replacement = await service.create_authenticated(first, request(), definition())
    assert replacement is not None
    clock.now_value += timedelta(seconds=2)
    assert await service.respond_authenticated(first, replacement.id, "yes") is None


async def test_revoked_context_is_denied_and_concurrent_consumption_has_one_winner() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    owner_context = context()
    active = ActiveContexts({(owner_context.owner.id, owner_context.session.id)})
    store = MemoryStore()
    service = DeterministicConfirmationService(store, clock, context_validator=active)
    pending = await service.create_authenticated(owner_context, request(), definition())
    assert pending is not None
    authorization = await service.respond_authenticated(owner_context, pending.id, "confirm")
    assert authorization is not None

    results = await asyncio.gather(
        service.consume_authenticated(owner_context, authorization, request()),
        service.consume_authenticated(owner_context, authorization, request()),
    )
    assert results.count(True) == 1
    assert "private payload" not in repr(store.audits)

    active.active.clear()
    assert await service.create_authenticated(owner_context, request(), definition()) is None
    assert any(event.event_type == "confirmation.create.denied" for event in store.audits)
