import asyncio
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
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, ScheduledTaskUpdateCommand, TaskState
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.persistence.models import AuditEventModel, PendingConfirmationModel, ScheduledTaskModel, ScheduledTaskRunModel
from tara_api.persistence.repositories.tasks import SqlAlchemyScheduledTaskRepository
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.safety.clock import SystemClock
from tara_api.safety.confirmations import DeterministicConfirmationService
from tara_api.safety.policy import DeterministicActionPolicyService
from tara_api.tasks.mapping import CapabilityTaskMapper
from tara_api.tasks.payloads import TaskPayloadProtector
from tara_api.tasks.scheduler import ScheduledTaskScheduler
from tara_api.tasks.service import ScheduledTask, ScheduledTaskService


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


class _FailingSchedulerExecutor:
    async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
        return ToolResult(ToolResultStatus.DENIED, "safe denial")


class _CountingSchedulerExecutor:
    def __init__(self) -> None:
        self.invocations = 0

    async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
        self.invocations += 1
        return ToolResult(ToolResultStatus.SUCCEEDED, "safe success")


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
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
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


async def test_due_task_is_claimed_once_and_fails_closed_without_private_execution_payload(
    database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(
            SqlAlchemySafetyStore(database),
            SystemClock(),
            context_validator=authentication,
        ),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )
    task = await service.create(context, _command())
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    scheduler = ScheduledTaskScheduler(
        database,
        registry,
        _FailingSchedulerExecutor(),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        poll_seconds=1,
    )
    assert sum(await asyncio.gather(*(scheduler.tick(now) for _ in range(10)))) == 1
    assert await scheduler.tick(now) == 0

    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        runs = list(
            (
                await database_session.scalars(
                    select(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task.id)
                )
            ).all()
        )
    assert row is not None
    assert row.state == "failed"
    assert row.enabled is False
    assert row.claim_id is None
    assert row.last_outcome == "task_execution_denied"
    assert len(runs) == 1
    assert runs[0].state == "failed"
    assert runs[0].error_code == "task_execution_denied"


async def test_scheduler_global_dispatch_bound_leaves_remaining_due_work_for_later_tick(database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )
    first = await service.create(context, _command(idempotency_key="global-one"))
    second = await service.create(context, _command(idempotency_key="global-two"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        for task_id in (first.id, second.id):
            row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id))
            assert row is not None
            row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    executor = _CountingSchedulerExecutor()
    scheduler = ScheduledTaskScheduler(
        database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        due_batch_size=8, maximum_concurrency=1, maximum_per_owner=1,
    )
    assert await scheduler.tick(now) == 1
    assert executor.invocations == 1
    assert await scheduler.tick(now) == 1
    assert executor.invocations == 2


async def test_scheduler_releases_unused_owner_limiter_entry(database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    scheduler = ScheduledTaskScheduler(
        database,
        CapabilityRegistry(AllowlistedFilesystemListTool((root,))),
        _FailingSchedulerExecutor(),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )

    limiter = await scheduler._retain_owner_limit(context.owner.id)  # noqa: SLF001
    assert context.owner.id in scheduler._owner_limits  # noqa: SLF001
    await scheduler._release_owner_limit(context.owner.id, limiter)  # noqa: SLF001
    assert context.owner.id not in scheduler._owner_limits  # noqa: SLF001


async def test_owner_scoped_creation_is_idempotent(database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)

    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)
    command = _command()

    first = await service.create(context, command)
    second = await service.create(context, command)

    assert first.id == second.id


async def test_concurrent_equivalent_consequential_creates_share_task_and_proposal(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication, additional_tools=(_ConsequentialTestTool(),))
    command = _command(
        capability_id="fake.scheduled.send",
        target="private-recipient",
        parameters={"content": "private-payload"},
    )

    tasks = await asyncio.gather(*(service.create(context, command) for _ in range(10)))

    assert len({task.id for task in tasks}) == 1
    assert len({task.confirmation_id for task in tasks}) == 1
    async with database.session() as database_session:
        task_count = await database_session.scalar(select(func.count()).select_from(ScheduledTaskModel))
        proposal_count = await database_session.scalar(
            select(func.count()).select_from(PendingConfirmationModel)
        )
    assert task_count == 1
    assert proposal_count == 1


async def test_concurrent_approval_has_one_activation_winner(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication, additional_tools=(_ConsequentialTestTool(),))
    task = await service.create(
        context,
        _command(
            capability_id="fake.scheduled.send",
            target="private-recipient",
            parameters={"content": "private-payload"},
        ),
    )

    results = await asyncio.gather(
        service.approve_confirmation(context, task.id, "yes"),
        service.approve_confirmation(context, task.id, "yes"),
        return_exceptions=True,
    )

    activated = [result for result in results if getattr(result, "state", None) is TaskState.ACTIVE]
    assert len(activated) == 1
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        consumption_count = await database_session.scalar(
            select(func.count()).select_from(PendingConfirmationModel).where(
                PendingConfirmationModel.id == task.confirmation_id,
                PendingConfirmationModel.consumed_at.is_not(None),
            )
        )
    assert row is not None and row.state == TaskState.ACTIVE.value and row.next_run_at is not None
    assert consumption_count == 1


async def test_concurrent_mismatched_payload_rejects_without_second_task(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)

    results = await asyncio.gather(
        service.create(context, _command(instruction="First payload")),
        service.create(context, _command(instruction="Different payload")),
        return_exceptions=True,
    )

    assert sum(isinstance(result, ScheduledTask) for result in results) == 1
    assert any(
        isinstance(result, ValueError) and str(result) == "idempotency_key_payload_mismatch"
        for result in results
    )
    async with database.session() as database_session:
        task_count = await database_session.scalar(select(func.count()).select_from(ScheduledTaskModel))
    assert task_count == 1


async def test_idempotency_keys_are_isolated_by_authenticated_session(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    owner, second_session, _token = await authentication.login("owner@example.test", "safe-password")
    second_context = AuthenticatedOwnerContext(owner, second_session)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)

    first = await service.create(context, _command())
    second = await service.create(second_context, _command())

    assert first.id != second.id


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
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
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


async def test_owner_session_approval_consumes_once_and_activates_task(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(
        database,
        root,
        authentication,
        additional_tools=(_ConsequentialTestTool(),),
    )
    task = await service.create(
        context,
        _command(
            capability_id="fake.scheduled.send",
            target="private-recipient",
            parameters={"content": "private-payload"},
        ),
    )

    approved = await service.approve_confirmation(context, task.id, "yes")

    assert approved is not None
    assert approved.state is TaskState.ACTIVE
    assert approved.enabled is True
    assert approved.schedule.next_after(datetime(2026, 8, 3, tzinfo=UTC)) is not None
    with pytest.raises(ValueError, match="task_not_pending_confirmation"):
        await service.approve_confirmation(context, task.id, "yes")
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
    assert row is not None
    assert row.confirmation_status == "executing"
    assert row.next_run_at is not None


@pytest.mark.parametrize(
    "field,value",
    [
        ("capability_id", "unknown.capability"),
        ("target_identity_hash", "0" * 64),
        ("parameters_hash", "1" * 64),
        ("instruction", "changed instruction"),
        ("timezone", "Asia/Kolkata"),
    ],
)
async def test_changed_persisted_binding_rejects_task_confirmation(
    database: Database,
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication, additional_tools=(_ConsequentialTestTool(),))
    task = await service.create(
        context,
        _command(
            capability_id="fake.scheduled.send",
            target="private-recipient",
            parameters={"content": "private-payload"},
        ),
    )
    async with database.unit_of_work() as unit:
        row = await unit.scheduled_tasks.get_for_owner(task.id, context.owner.id)
        assert row is not None
        setattr(row, field, value)

    with pytest.raises(ValueError, match="task_confirmation_binding_invalid"):
        await service.approve_confirmation(context, task.id, "yes")
    current = await service.get(context, task.id)
    assert current is not None
    assert current.state is TaskState.PENDING_CONFIRMATION
    assert current.enabled is False


async def test_bound_field_update_invalidates_attached_confirmation(
    database: Database,
    tmp_path: Path,
) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication, additional_tools=(_ConsequentialTestTool(),))
    task = await service.create(
        context,
        _command(
            capability_id="fake.scheduled.send",
            target="private-recipient",
            parameters={"content": "private-payload"},
        ),
    )

    updated = await service.update(context, task.id, ScheduledTaskUpdateCommand(instruction="Changed private instruction"))

    assert updated is not None
    assert updated.state is TaskState.PENDING_CONFIRMATION
    assert updated.enabled is False
    assert updated.confirmation_id is None
    assert updated.confirmation_expires_at is None
    with pytest.raises(ValueError, match="task_confirmation_missing"):
        await service.approve_confirmation(context, task.id, "yes")
