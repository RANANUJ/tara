"""M3 tests for deterministic permission, confirmation, and tool-execution safety."""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tara_api.domain.models import (
    ActionRiskLevel,
    AuditEvent,
    ConfirmationStatus,
    JsonValue,
    PendingConfirmation,
    PermissionScope,
    ToolDefinition,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
)
from tara_api.persistence.database import Database
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.persistence.types import ConfirmationStatus as PersistenceConfirmationStatus
from tara_api.safety.confirmations import DeterministicConfirmationService
from tara_api.safety.permissions import DefaultDenyPermissionService
from tara_api.safety.policy import DeterministicActionPolicyService
from tara_api.safety.registry import InMemoryToolRegistry
from tara_api.safety.tool_executor import SafetyToolExecutor


class FixedClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class InMemorySafetyStore:
    def __init__(self) -> None:
        self.confirmations: dict[object, PendingConfirmation] = {}
        self.audits: list[AuditEvent] = []

    async def publish(self, event: AuditEvent) -> None:
        self.audits.append(event)

    async def create_confirmation(self, confirmation: PendingConfirmation, audit_event: AuditEvent) -> None:
        self.confirmations[confirmation.id] = confirmation
        self.audits.append(audit_event)

    async def get_confirmation(self, confirmation_id: object) -> PendingConfirmation | None:
        return self.confirmations.get(confirmation_id)

    async def set_confirmation_status(
        self,
        confirmation_id: object,
        status: ConfirmationStatus,
        occurred_at: datetime,
        audit_event: AuditEvent,
    ) -> PendingConfirmation | None:
        confirmation = self.confirmations.get(confirmation_id)
        if confirmation is None or confirmation.status == ConfirmationStatus.EXECUTING:
            return None
        if confirmation.status not in {
            ConfirmationStatus.AWAITING_CONFIRMATION,
            ConfirmationStatus.APPROVED,
        }:
            return None
        if status == ConfirmationStatus.APPROVED and confirmation.status != ConfirmationStatus.AWAITING_CONFIRMATION:
            return None
        updated = replace(confirmation, status=status)
        self.confirmations[confirmation_id] = updated
        self.audits.append(audit_event)
        return updated

    async def consume_confirmation(
        self,
        confirmation_id: object,
        request_hash: str,
        occurred_at: datetime,
        audit_event: AuditEvent,
    ) -> bool:
        confirmation = self.confirmations.get(confirmation_id)
        if (
            confirmation is None
            or confirmation.status != ConfirmationStatus.APPROVED
            or confirmation.request_hash != request_hash
            or confirmation.expires_at <= occurred_at
        ):
            return False
        self.confirmations[confirmation_id] = replace(confirmation, status=ConfirmationStatus.EXECUTING)
        self.audits.append(audit_event)
        return True


class FakeTool:
    def __init__(self, definition: ToolDefinition) -> None:
        self.definition = definition
        self.calls = 0

    def validate_arguments(self, arguments: Mapping[str, JsonValue]) -> dict[str, object]:
        target = arguments.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("target is required")
        return {"target": target}

    async def execute(self, request: ToolRequest, validated_arguments: dict[str, object]) -> ToolResult:
        self.calls += 1
        return ToolResult(ToolResultStatus.SUCCEEDED, "Fake tool executed")


def tool_definition(name: str, capability: str, risk: ActionRiskLevel) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        version="1",
        permission_scope=PermissionScope(capability),
        risk_level=risk,
        summary_template=f"perform {name}",
    )


def request_for(name: str, target: str = "recipient") -> ToolRequest:
    return ToolRequest(name, "1", {"target": target, "content": "sensitive message body"})


def build_executor(
    tool: FakeTool,
    clock: FixedClock,
    granted: bool = True,
) -> tuple[SafetyToolExecutor, DeterministicConfirmationService, InMemorySafetyStore]:
    store = InMemorySafetyStore()
    scope = (tool.definition.permission_scope,) if granted else ()
    confirmations = DeterministicConfirmationService(store, clock)
    executor = SafetyToolExecutor(
        InMemoryToolRegistry((tool,)),
        DefaultDenyPermissionService(scope),
        DeterministicActionPolicyService(),
        confirmations,
        store,
        clock,
    )
    return executor, confirmations, store


async def test_permissions_default_deny_and_read_only_disabled_tool(database: Database) -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    tool = FakeTool(tool_definition("calendar.read", "calendar.read", ActionRiskLevel.READ_ONLY))
    executor, _, _ = build_executor(tool, clock, granted=False)

    result = await executor.execute(request_for("calendar.read"))

    assert result.status == ToolResultStatus.DENIED
    assert tool.calls == 0
    assert DefaultDenyPermissionService().is_allowed(tool.definition.permission_scope, request_for("calendar.read")) is False


@pytest.mark.parametrize(
    ("name", "capability", "risk"),
    [
        ("message.send", "messages.send", ActionRiskLevel.LOCAL_REVERSIBLE),
        ("call.place", "calls.place", ActionRiskLevel.READ_ONLY),
        ("memory.delete", "memory.delete", ActionRiskLevel.LOCAL_REVERSIBLE),
        ("payment.submit", "financial.submit", ActionRiskLevel.LOCAL_REVERSIBLE),
    ],
)
async def test_consequential_actions_are_blocked_without_confirmation(
    name: str,
    capability: str,
    risk: ActionRiskLevel,
) -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    tool = FakeTool(tool_definition(name, capability, risk))
    executor, _, _ = build_executor(tool, clock)

    result = await executor.execute(request_for(name))

    assert result.status == ToolResultStatus.CONFIRMATION_REQUIRED
    assert result.confirmation is not None
    assert tool.calls == 0


async def test_confirmation_authorizes_exactly_once_and_modified_arguments_invalidate() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    tool = FakeTool(tool_definition("message.send", "messages.send", ActionRiskLevel.OUTWARD_FACING))
    executor, confirmations, store = build_executor(tool, clock)
    request = request_for("message.send")

    pending = (await executor.execute(request)).confirmation
    assert pending is not None
    authorization = await confirmations.respond(pending.id, "Yes")
    assert authorization is not None

    changed_request = request_for("message.send", target="different-recipient")
    changed_result = await executor.execute(changed_request, authorization)
    assert changed_result.status == ToolResultStatus.DENIED
    assert store.confirmations[pending.id].status == ConfirmationStatus.INVALIDATED
    assert tool.calls == 0

    second_pending = (await executor.execute(request)).confirmation
    assert second_pending is not None
    second_authorization = await confirmations.respond(second_pending.id, "confirm")
    assert second_authorization is not None
    assert (await executor.execute(request, second_authorization)).status == ToolResultStatus.SUCCEEDED
    assert (await executor.execute(request, second_authorization)).status == ToolResultStatus.DENIED
    assert tool.calls == 1


async def test_expired_rejected_negative_and_ambiguous_responses_cannot_authorize() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    tool = FakeTool(tool_definition("call.place", "calls.place", ActionRiskLevel.CALL))
    executor, confirmations, store = build_executor(tool, clock)

    expired_pending = (await executor.execute(request_for("call.place"))).confirmation
    assert expired_pending is not None
    clock.current += timedelta(minutes=3)
    assert await confirmations.respond(expired_pending.id, "yes") is None
    assert store.confirmations[expired_pending.id].status == ConfirmationStatus.EXPIRED

    clock.current = datetime(2026, 8, 1, tzinfo=UTC)
    rejected_pending = (await executor.execute(request_for("call.place"))).confirmation
    assert rejected_pending is not None
    assert await confirmations.respond(rejected_pending.id, "no") is None
    assert store.confirmations[rejected_pending.id].status == ConfirmationStatus.REJECTED

    ambiguous_pending = (await executor.execute(request_for("call.place"))).confirmation
    assert ambiguous_pending is not None
    assert await confirmations.respond(ambiguous_pending.id, "maybe later") is None
    assert store.confirmations[ambiguous_pending.id].status == ConfirmationStatus.AWAITING_CONFIRMATION
    assert tool.calls == 0


async def test_unknown_and_invalid_tools_never_call_a_fake_executor() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    tool = FakeTool(tool_definition("calendar.read", "calendar.read", ActionRiskLevel.READ_ONLY))
    executor, _, _ = build_executor(tool, clock)

    unknown = await executor.execute(request_for("unknown.tool"))
    invalid = await executor.execute(ToolRequest("calendar.read", "1", {"target": ""}))

    assert unknown.status == ToolResultStatus.UNKNOWN_TOOL
    assert invalid.status == ToolResultStatus.INVALID
    assert tool.calls == 0


async def test_audit_events_do_not_record_sensitive_tool_payloads() -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    tool = FakeTool(tool_definition("message.send", "messages.send", ActionRiskLevel.OUTWARD_FACING))
    executor, _, store = build_executor(tool, clock)
    secret = "sensitive message body"

    await executor.execute(request_for("message.send"))

    rendered = json.dumps(
        [{"event_type": event.event_type, "metadata": event.safe_metadata} for event in store.audits]
    )
    assert secret not in rendered
    assert "content" not in rendered


async def test_sqlalchemy_confirmation_consumption_is_atomic_and_audited(database: Database) -> None:
    clock = FixedClock(datetime(2026, 8, 1, tzinfo=UTC))
    store = SqlAlchemySafetyStore(database)
    confirmations = DeterministicConfirmationService(store, clock)
    definition = tool_definition("message.send", "messages.send", ActionRiskLevel.OUTWARD_FACING)
    request = request_for("message.send")

    pending = await confirmations.create(request, definition)
    authorization = await confirmations.respond(pending.id, "approve")
    assert authorization is not None
    results = await asyncio.gather(
        confirmations.consume(authorization, request),
        confirmations.consume(authorization, request),
    )

    assert results.count(True) == 1
    assert results.count(False) == 1
    async with database.unit_of_work() as unit_of_work:
        persisted = await unit_of_work.confirmations.get_by_id(pending.id)
        audits = await unit_of_work.audit_events.list()
    assert persisted is not None
    assert persisted.status == PersistenceConfirmationStatus.EXECUTING
    assert any(event.event_type == "confirmation.consumed" for event in audits)
    assert "sensitive message body" not in json.dumps([event.safe_metadata for event in audits])
