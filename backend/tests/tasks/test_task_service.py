from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.models import (
    ActionRiskLevel,
    JsonValue,
    PermissionScope,
    ToolDefinition,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
)
from tara_api.domain.protocols import Tool
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, TaskState
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.persistence.models import AuditEventModel, PendingConfirmationModel, ScheduledTaskModel
from tara_api.persistence.repositories.tasks import SqlAlchemyScheduledTaskRepository
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.safety.clock import SystemClock
from tara_api.safety.confirmations import DeterministicConfirmationService
from tara_api.safety.policy import DeterministicActionPolicyService
from tara_api.tasks.mapping import CapabilityTaskMapper
from tara_api.tasks.service import ScheduledTaskService


class _ConsequentialTestTool:
    definition = ToolDefinition(
        "fake.scheduled.send",
        "1",
        PermissionScope("fake.scheduled.send"),
        ActionRiskLevel.OUTWARD_FACING,
        "perform a non-production scheduled action",
    )

    def validate_arguments(self, arguments: Mapping[str, JsonValue]) -> dict[str, object]:
        if set(arguments) != {"target", "content"}:
            raise ValueError("invalid arguments")
        target = arguments["target"]
        content = arguments["content"]
        if not isinstance(target, str) or not isinstance(content, str):
            raise ValueError("invalid arguments")
        return {"target": target, "content": content}

    async def execute(
        self,
        _request: ToolRequest,
        _validated_arguments: dict[str, object],
    ) -> ToolResult:
        return ToolResult(ToolResultStatus.DENIED, "Test capability must not execute")


class _FailingConfirmationService(DeterministicConfirmationService):
    async def create_authenticated(
        self,
        _context: AuthenticatedOwnerContext,
        _request: ToolRequest,
        _definition: ToolDefinition,
    ) -> None:
        raise RuntimeError("private confirmation failure")


async def _authenticated_context(
    database: Database,
    email: str = "owner@example.test",
) -> tuple[AuthenticatedOwnerContext, AuthenticationService]:
    store = SqlAlchemyAuthenticationStore(database)
    authentication = AuthenticationService(
        store,
        store,
        Argon2idPasswordHasher(),
        SecureSessionTokenGenerator(),
        InMemoryLoginRateLimiter(),
        lambda: datetime.now(UTC),
        timedelta(hours=1),
        timedelta(hours=1),
    )
    await authentication.bootstrap(email, "safe-password")
    owner, session, _token = await authentication.login(email, "safe-password")
    return AuthenticatedOwnerContext(owner, session), authentication


def _service(
    database: Database,
    root: Path,
    authentication: AuthenticationService,
    *,
    enabled: bool = True,
    additional_tools: tuple[Tool, ...] = (),
    confirmations: DeterministicConfirmationService | None = None,
) -> ScheduledTaskService:
    registry = CapabilityRegistry(
        AllowlistedFilesystemListTool((root,)) if enabled else None,
        additional_tools=additional_tools,
    )
    return ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        confirmations
        or DeterministicConfirmationService(
            SqlAlchemySafetyStore(database),
            SystemClock(),
            context_validator=authentication,
        ),
    )


def _command(
    *,
    capability_id: str = "filesystem.list",
    target: str = ".",
    parameters: dict[str, str | int | bool | None] | None = None,
    instruction: str = "Drink water",
    idempotency_key: str = "one",
) -> ScheduledTaskCreateCommand:
    return ScheduledTaskCreateCommand(
        "Reminder",
        instruction,
        capability_id,
        target,
        parameters or {},
        ScheduleDefinition("UTC", datetime(2027, 1, 1, tzinfo=UTC)),
        idempotency_key,
    )


async def test_typed_registered_capability_creation_persists_safe_metadata(database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)

    task = await service.create(context, _command())

    assert task.state is TaskState.ACTIVE
    assert task.enabled is True
    assert task.capability_id == "filesystem.list"
    assert task.target_summary == "configured target"
    assert task.parameters_hash is not None
    assert task.confirmation_id is None
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
    assert row is not None
    assert row.target_identity_hash is not None
    assert row.parameters_hash is not None
    assert row.confirmation_binding_hash is not None
    assert row.risk_level == "read_only"
    assert row.next_run_at is not None
    assert not hasattr(row, "target")
    assert not hasattr(row, "parameters")


async def test_owner_scoped_creation_is_idempotent(database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)
    command = _command()

    first = await service.create(context, command)
    second = await service.create(context, command)

    assert first.id == second.id


@pytest.mark.parametrize(
    "service_enabled,command,error_code",
    [
        (True, _command(capability_id="unknown.capability"), "unknown_capability"),
        (False, _command(), "unknown_capability"),
        (True, _command(parameters={"unexpected": "value"}), "invalid_capability_arguments"),
    ],
)
async def test_typed_creation_rejects_unavailable_or_invalid_capability(
    database,
    tmp_path: Path,
    service_enabled: bool,
    command: ScheduledTaskCreateCommand,
    error_code: str,
) -> None:
    context, authentication = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match=error_code):
        await _service(database, root, authentication, enabled=service_enabled).create(context, command)


async def test_consequential_task_creates_one_authenticated_m14_proposal(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    tool = _ConsequentialTestTool()
    registry = CapabilityRegistry(
        AllowlistedFilesystemListTool((root,)),
        additional_tools=(tool,),
    )
    policy = DeterministicActionPolicyService()
    service = ScheduledTaskService(
        database,
        registry,
        policy,
        DeterministicConfirmationService(
            SqlAlchemySafetyStore(database),
            SystemClock(),
            context_validator=authentication,
        ),
    )
    command = _command(
        capability_id=tool.definition.name,
        target="private-recipient",
        parameters={"content": "private-payload"},
        instruction="Send the private briefing",
    )

    task = await service.create(context, command)
    duplicate = await service.create(context, command)

    assert task.id == duplicate.id
    assert task.state is TaskState.PENDING_CONFIRMATION
    assert task.enabled is False
    assert task.schedule.next_after(datetime(2027, 1, 2, tzinfo=UTC)) is None
    assert task.confirmation_id is not None
    assert task.confirmation_status == "awaiting_confirmation"
    assert task.confirmation_expires_at is not None
    async with database.session() as database_session:
        row = await database_session.scalar(
            select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id)
        )
        proposal_count = await database_session.scalar(
            select(func.count()).select_from(PendingConfirmationModel)
        )
        audit_events = list((await database_session.scalars(select(AuditEventModel))).all())
    assert row is not None
    assert proposal_count == 1
    assert row.next_run_at is None
    assert row.target_summary == "configured target"
    assert row.confirmation_expires_at == task.confirmation_expires_at
    assert not hasattr(row, "target")
    assert not hasattr(row, "parameters")
    assert not hasattr(row, "confirmation_secret")
    assert "private-recipient" not in repr(audit_events)
    assert "private-payload" not in repr(audit_events)

    confirmation = await SqlAlchemySafetyStore(database).get_confirmation(task.confirmation_id)
    assert confirmation is not None
    assert (confirmation.owner_id, confirmation.session_id) == (context.owner.id, context.session.id)
    mapped = CapabilityTaskMapper(registry, policy).map(command)
    expected_request = ScheduledTaskService._confirmation_request(task.id, command, mapped)
    assert confirmation.request_hash == expected_request.canonical_hash()
    assert row.confirmation_binding_hash == mapped.binding_hash
    assert row.target_identity_hash == mapped.target_hash
    assert row.parameters_hash == mapped.parameters_hash


async def test_consequential_proposal_failure_leaves_task_non_executable(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    failing_service = _service(
        database,
        root,
        authentication,
        additional_tools=(_ConsequentialTestTool(),),
        confirmations=_FailingConfirmationService(
            SqlAlchemySafetyStore(database),
            SystemClock(),
            context_validator=authentication,
        ),
    )
    command = _command(
        capability_id="fake.scheduled.send",
        target="private-recipient",
        parameters={"content": "private-payload"},
    )

    with pytest.raises(ValueError, match="task_confirmation_unavailable"):
        await failing_service.create(context, command)

    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel))
    assert row is not None
    assert row.state == TaskState.PENDING_CONFIRMATION.value
    assert row.enabled is False
    assert row.next_run_at is None
    assert row.confirmation_id is None


async def test_consequential_attachment_failure_is_safe_and_service_remains_usable(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    async def reject_attachment(
        self: SqlAlchemyScheduledTaskRepository,
        task_id: object,
        owner_id: object,
        confirmation_id: object,
        status: object,
        binding_hash: object,
        expires_at: object,
    ) -> None:
        return None

    monkeypatch.setattr(SqlAlchemyScheduledTaskRepository, "attach_confirmation", reject_attachment)
    service = _service(
        database,
        root,
        authentication,
        additional_tools=(_ConsequentialTestTool(),),
    )
    with pytest.raises(ValueError, match="task_confirmation_unavailable"):
        await service.create(
            context,
            _command(
                capability_id="fake.scheduled.send",
                target="private-recipient",
                parameters={"content": "private-payload"},
            ),
        )

    read_only = await service.create(context, _command(idempotency_key="read-only-after-failure"))
    assert read_only.state is TaskState.ACTIVE
