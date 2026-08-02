"""Non-production consequential-action harness guarded by deterministic confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tara_api.auth.service import AuthenticationService
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.models import ActionRiskLevel, AuditEvent, PermissionScope, ToolDefinition, ToolRequest
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.safety.confirmations import DeterministicConfirmationService


@dataclass(frozen=True, slots=True)
class ConsequentialAction:
    id: UUID
    confirmation_id: UUID
    owner_id: UUID
    session_id: UUID
    target: str
    state: str
    created_at: datetime


class FakeConsequentialActionService:
    """Records a harmless fake send after exact owner/session confirmation only."""

    definition = ToolDefinition("fake.consequential.send", "1", PermissionScope("fake.consequential.send"), ActionRiskLevel.OUTWARD_FACING, "perform the non-production test action", idempotent=True)

    def __init__(self, confirmations: DeterministicConfirmationService, store: SqlAlchemySafetyStore, authentication: AuthenticationService, *, enabled: bool, uncertain: bool = False) -> None:
        self._confirmations = confirmations
        self._store = store
        self._authentication = authentication
        self._enabled = enabled
        self._uncertain = uncertain
        self._actions: dict[UUID, ConsequentialAction] = {}
        self._by_confirmation: dict[UUID, UUID] = {}

    async def propose(self, context: AuthenticatedOwnerContext, target: str) -> ConsequentialAction | None:
        if not self._enabled or not await self._authentication.is_context_active(context):
            return None
        normalized = " ".join(target.split())
        if not normalized or len(normalized) > 64:
            return None
        request = ToolRequest(self.definition.name, self.definition.version, {"target": normalized})
        confirmation = await self._confirmations.create_authenticated(context, request, self.definition)
        if confirmation is None:
            return None
        action = ConsequentialAction(uuid4(), confirmation.id, context.owner.id, context.session.id, normalized, "awaiting_confirmation", datetime.now(UTC))
        self._actions[action.id] = action
        self._by_confirmation[confirmation.id] = action.id
        return action

    async def respond(self, context: AuthenticatedOwnerContext, confirmation_id: UUID, response: str) -> ConsequentialAction | None:
        action_id = self._by_confirmation.get(confirmation_id)
        action = self._actions.get(action_id) if action_id else None
        if action is None or action.owner_id != context.owner.id or action.session_id != context.session.id:
            return None
        request = ToolRequest(self.definition.name, self.definition.version, {"target": action.target})
        authorization = await self._confirmations.respond_authenticated(context, confirmation_id, response)
        if authorization is None:
            return action
        if not await self._confirmations.consume_authenticated(context, authorization, request):
            return action
        state = "uncertain" if self._uncertain else "succeeded"
        completed = ConsequentialAction(action.id, action.confirmation_id, action.owner_id, action.session_id, action.target, state, action.created_at)
        self._actions[action.id] = completed
        await self._store.publish(AuditEvent("fake_consequential.executed", state, datetime.now(UTC), str(action.id), {"capability": self.definition.name, "target_category": "synthetic"}))
        return completed

    async def get(self, context: AuthenticatedOwnerContext, action_id: UUID) -> ConsequentialAction | None:
        if not await self._authentication.is_context_active(context):
            return None
        action = self._actions.get(action_id)
        return action if action and action.owner_id == context.owner.id and action.session_id == context.session.id else None
