import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
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
from tara_api.persistence.models import AuditEventModel, PendingConfirmationModel, ScheduledTaskModel, ScheduledTaskRunModel, TaskExecutionPayloadModel
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


async def test_cancellation_before_poll_prevents_claim_and_revokes_payload(database, tmp_path: Path) -> None:
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
    task = await service.create(context, _command(idempotency_key="cancel-before-poll"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    assert await service.cancel(context, task.id)
    executor = _CountingSchedulerExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    assert await scheduler.tick(now) == 0
    assert executor.invocations == 0
    async with database.session() as database_session:
        payload = await database_session.scalar(select(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.task_id == task.id))
        run_count = await database_session.scalar(select(func.count()).select_from(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task.id))
    assert payload is not None and payload.revoked_at is not None
    assert run_count == 0


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


async def test_cancellation_after_claim_but_before_execution(database: Database, tmp_path: Path) -> None:
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
    task = await service.create(
        context,
        _command(
            capability_id="filesystem.list",
            instruction="Recurring test",
            parameters={"target": "."},
            idempotency_key="cancel-after-claim",
        ),
    )
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    async with database.unit_of_work() as unit:
        claimed = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
        assert len(claimed) == 1
        assert claimed[0][0].id == task.id

    assert await service.cancel(context, task.id) is True

    executor = _CountingSchedulerExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    assert await scheduler.tick(now) == 0
    assert executor.invocations == 0

    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        run = await database_session.scalar(select(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task.id))
        payload = await database_session.scalar(select(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.task_id == task.id))
    assert row is not None
    assert row.state == "canceled"
    assert row.enabled is False
    assert row.claim_id is None
    assert row.next_run_at is None
    assert run is not None and run.state == "canceled" and run.error_code == "task_canceled"
    assert payload is not None and payload.revoked_at is not None


async def test_cancellation_while_capability_execution_is_blocked(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    class _BlockingExecutor:
        def __init__(self) -> None:
            self.started_event = asyncio.Event()
            self.release_event = asyncio.Event()
            self.invocations = 0

        async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
            self.invocations += 1
            self.started_event.set()
            await self.release_event.wait()
            return ToolResult(ToolResultStatus.SUCCEEDED, "unblocked success")

    tool = AllowlistedFilesystemListTool((root,))
    registry = CapabilityRegistry(tool)
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )
    task = await service.create(context, _command(idempotency_key="cancel-while-blocked"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    executor = _BlockingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    tick_task = asyncio.create_task(scheduler.tick(now))
    await executor.started_event.wait()
    assert executor.invocations == 1

    assert await service.cancel(context, task.id) is True

    executor.release_event.set()
    await tick_task

    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        run = await database_session.scalar(select(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task.id))
        payload = await database_session.scalar(select(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.task_id == task.id))
    assert row is not None
    assert row.state == "canceled"
    assert row.enabled is False
    assert row.claim_id is None
    assert row.next_run_at is None
    assert run is not None and run.state == "canceled" and run.error_code == "task_canceled"
    assert payload is not None and payload.revoked_at is not None


async def test_repeated_cancellation_is_idempotent(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)
    task = await service.create(context, _command(idempotency_key="repeated-cancel"))

    assert await service.cancel(context, task.id) is True
    assert await service.cancel(context, task.id) is True
    assert await service.cancel(context, task.id) is True

    current = await service.get(context, task.id)
    assert current is not None
    assert current.state is TaskState.CANCELED
    assert current.enabled is False
    async with database.session() as database_session:
        payload = await database_session.scalar(select(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.task_id == task.id))
    assert payload is not None and payload.revoked_at is not None


async def test_foreign_owner_cancellation_rejected(database: Database, tmp_path: Path) -> None:
    context1, authentication = await _authenticated_context(database, "owner1@example.test")
    now = datetime.now(UTC)
    foreign_owner = Owner(id=uuid4(), email="foreign@example.test", created_at=now)
    foreign_session = OwnerSession(id=uuid4(), owner_id=foreign_owner.id, issued_at=now, expires_at=now + timedelta(hours=1), last_used_at=now, revoked_at=None, client_label=None)
    context2 = AuthenticatedOwnerContext(foreign_owner, foreign_session)

    root = tmp_path / "root"
    root.mkdir()
    service = _service(database, root, authentication)
    task = await service.create(context1, _command(idempotency_key="foreign-cancel"))

    assert await service.cancel(context2, task.id) is False

    current = await service.get(context1, task.id)
    assert current is not None
    assert current.state is TaskState.ACTIVE
    assert current.enabled is True
    async with database.session() as database_session:
        payload = await database_session.scalar(select(TaskExecutionPayloadModel).where(TaskExecutionPayloadModel.task_id == task.id))
    assert payload is not None and payload.revoked_at is None


async def test_timeout_creates_exactly_one_timed_out_terminal_outcome(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    class _HangingExecutor:
        def __init__(self) -> None:
            self.release_event = asyncio.Event()

        async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
            await self.release_event.wait()
            return ToolResult(ToolResultStatus.SUCCEEDED, "eventually done")

    executor = _HangingExecutor()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )
    task = await service.create(context, _command(idempotency_key="timeout-single-outcome"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    scheduler = ScheduledTaskScheduler(
        database,
        registry,
        executor,
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        run_timeout_seconds=1,
    )
    scheduler._run_timeout_seconds = 0.05

    assert await scheduler.tick(now) == 1
    executor.release_event.set()

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
    assert row.next_run_at is None
    assert row.last_outcome == "task_execution_timed_out"
    assert len(runs) == 1
    assert runs[0].state == "failed"
    assert runs[0].error_code == "task_execution_timed_out"


async def test_late_completion_after_timeout_cannot_overwrite_state(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    class _ControllableExecutor:
        def __init__(self) -> None:
            self.started_event = asyncio.Event()
            self.release_event = asyncio.Event()

        async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
            self.started_event.set()
            await self.release_event.wait()
            return ToolResult(ToolResultStatus.SUCCEEDED, "late success")

    executor = _ControllableExecutor()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )
    task = await service.create(context, _command(idempotency_key="late-after-timeout"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    scheduler = ScheduledTaskScheduler(
        database,
        registry,
        executor,
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        run_timeout_seconds=1,
    )
    scheduler._run_timeout_seconds = 0.05

    tick_task = asyncio.create_task(scheduler.tick(now))
    await executor.started_event.wait()
    await tick_task

    executor.release_event.set()
    await asyncio.sleep(0.01)

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
    assert row.next_run_at is None
    assert row.last_outcome == "task_execution_timed_out"
    assert len(runs) == 1
    assert runs[0].state == "failed"
    assert runs[0].error_code == "task_execution_timed_out"


async def test_late_completion_after_cancellation_cannot_overwrite_state(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    class _ControllableExecutor:
        def __init__(self) -> None:
            self.started_event = asyncio.Event()
            self.release_event = asyncio.Event()

        async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
            self.started_event.set()
            await self.release_event.wait()
            return ToolResult(ToolResultStatus.SUCCEEDED, "late success after cancel")

    executor = _ControllableExecutor()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )
    task = await service.create(context, _command(idempotency_key="late-after-cancel"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    scheduler = ScheduledTaskScheduler(
        database,
        registry,
        executor,
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )

    tick_task = asyncio.create_task(scheduler.tick(now))
    await executor.started_event.wait()

    assert await service.cancel(context, task.id) is True

    executor.release_event.set()
    await tick_task

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
    assert row.state == "canceled"
    assert row.enabled is False
    assert row.claim_id is None
    assert row.next_run_at is None
    assert len(runs) == 1
    assert runs[0].state == "canceled"
    assert runs[0].error_code == "task_canceled"


async def test_limiter_released_after_timeout_and_cancellation(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    class _ControllableExecutor:
        def __init__(self) -> None:
            self.started_event = asyncio.Event()
            self.release_event = asyncio.Event()

        async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
            self.started_event.set()
            await self.release_event.wait()
            return ToolResult(ToolResultStatus.SUCCEEDED, "done")

    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )

    executor1 = _ControllableExecutor()
    scheduler1 = ScheduledTaskScheduler(
        database, registry, executor1, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        maximum_concurrency=2, maximum_per_owner=1,
    )
    task1 = await service.create(context, _command(idempotency_key="limiter-cancel"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task1.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    tick_task1 = asyncio.create_task(scheduler1.tick(now))
    await executor1.started_event.wait()
    await service.cancel(context, task1.id)
    executor1.release_event.set()
    await tick_task1

    assert scheduler1._global._value == 2  # noqa: SLF001
    assert context.owner.id not in scheduler1._owner_limits  # noqa: SLF001

    executor2 = _ControllableExecutor()
    scheduler2 = ScheduledTaskScheduler(
        database, registry, executor2, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        maximum_concurrency=2, maximum_per_owner=1, run_timeout_seconds=1,
    )
    scheduler2._run_timeout_seconds = 0.05

    task2 = await service.create(context, _command(idempotency_key="limiter-timeout"))
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task2.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    tick_task2 = asyncio.create_task(scheduler2.tick(now))
    await executor2.started_event.wait()
    await tick_task2
    executor2.release_event.set()

    assert scheduler2._global._value == 2  # noqa: SLF001
    assert context.owner.id not in scheduler2._owner_limits  # noqa: SLF001


async def test_payload_revoked_or_replaced_while_claimed_prevents_execution(database: Database, tmp_path: Path) -> None:
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

    task_a = await service.create(context, _command(idempotency_key="payload-revoked-claimed"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_a.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    async with database.unit_of_work() as unit:
        claimed = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
        assert len(claimed) == 1
        await unit.scheduled_tasks.revoke_payload(task_a.id, context.owner.id, now)

    executor = _CountingSchedulerExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    await scheduler._process(claimed[0][0], claimed[0][1], now)  # noqa: SLF001
    assert executor.invocations == 0

    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_a.id))
    assert row is not None and row.state == "failed" and row.last_outcome == "task_payload_unavailable"

    task_b = await service.create(context, _command(idempotency_key="payload-replaced-claimed"))
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_b.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    async with database.unit_of_work() as unit:
        claimed_b = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
        assert len(claimed_b) == 1
        await unit.scheduled_tasks.replace_payload(
            task_b.id, context.owner.id, capability_id="filesystem.list", binding_hash="mismatched_binding_hash",
            payload_version=1, key_version="1", nonce=b"0" * 12, ciphertext=b"fake", now=now,
        )

    await scheduler._process(claimed_b[0][0], claimed_b[0][1], now)  # noqa: SLF001
    assert executor.invocations == 0

    async with database.session() as database_session:
        row_b = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_b.id))
    assert row_b is not None and row_b.state == "failed" and row_b.last_outcome == "task_payload_unavailable"


async def test_pre_execution_invalidation_prevents_capability_invocation(database: Database, tmp_path: Path) -> None:
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
    now = datetime.now(UTC)

    cases = [
        ("pause", lambda s, t: s.pause(context, t.id)),
        ("disable", lambda s, t: s.disable(context, t.id)),
        ("delete", lambda s, t: s.delete(context, t.id)),
    ]

    for key, mutate in cases:
        task = await service.create(context, _command(idempotency_key=f"pre-exec-{key}"))
        async with database.session() as database_session:
            row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
            assert row is not None
            row.next_run_at = now - timedelta(seconds=1)
            await database_session.commit()

        async with database.unit_of_work() as unit:
            claimed = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
            assert len(claimed) == 1

        await mutate(service, task)

        executor = _CountingSchedulerExecutor()
        scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
        await scheduler._process(claimed[0][0], claimed[0][1], now)  # noqa: SLF001
        assert executor.invocations == 0, f"executor invoked for {key}"

    task_binding = await service.create(context, _command(idempotency_key="pre-exec-binding-mismatch"))
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_binding.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    async with database.unit_of_work() as unit:
        claimed_binding = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
        assert len(claimed_binding) == 1
        row_claimed = await unit.scheduled_tasks.get_for_owner(task_binding.id, context.owner.id)
        assert row_claimed is not None
        row_claimed.confirmation_binding_hash = "changed_binding_hash"

    executor = _CountingSchedulerExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    await scheduler._process(claimed_binding[0][0], claimed_binding[0][1], now)  # noqa: SLF001
    assert executor.invocations == 0


async def test_recurring_next_run_at_not_written_after_invalidation_or_cancellation(database: Database, tmp_path: Path) -> None:
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

    actions = [
        ("cancel", lambda s, t: s.cancel(context, t.id)),
        ("pause", lambda s, t: s.pause(context, t.id)),
        ("disable", lambda s, t: s.disable(context, t.id)),
        ("delete", lambda s, t: s.delete(context, t.id)),
    ]

    for idx, (name, action) in enumerate(actions):
        cmd = ScheduledTaskCreateCommand(
            "Recurring",
            "List files",
            "filesystem.list",
            ".",
            {},
            ScheduleDefinition("UTC", datetime(2027, 1, 1, tzinfo=UTC), interval_minutes=60),
            f"recurring-{name}-{idx}",
        )
        task = await service.create(context, cmd)
        await action(service, task)
        current = await service.get(context, task.id)
        if name == "delete":
            assert current is None
        else:
            assert current is not None
            async with database.session() as database_session:
                row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
            assert row is not None
            assert row.next_run_at is None


async def test_scheduler_remains_usable_after_timeout_or_cancellation(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()

    class _FailingFirstThenSuccessExecutor:
        def __init__(self) -> None:
            self.invocations: list[str] = []
            self.started_event = asyncio.Event()
            self.release_event = asyncio.Event()

        async def execute(self, request: ToolRequest, authorization: object | None = None) -> ToolResult:
            self.invocations.append(request.tool_name)
            if len(self.invocations) == 1:
                self.started_event.set()
                await self.release_event.wait()
                return ToolResult(ToolResultStatus.SUCCEEDED, "late")
            return ToolResult(ToolResultStatus.SUCCEEDED, "ok")

    executor = _FailingFirstThenSuccessExecutor()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    service = ScheduledTaskService(
        database,
        registry,
        DeterministicActionPolicyService(),
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )

    task1 = await service.create(context, _command(idempotency_key="usable-task-1"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row1 = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task1.id))
        assert row1 is not None
        row1.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    tick_task1 = asyncio.create_task(scheduler.tick(now))
    await executor.started_event.wait()
    await service.cancel(context, task1.id)
    executor.release_event.set()
    await tick_task1

    task2 = await service.create(context, _command(idempotency_key="usable-task-2"))
    async with database.session() as database_session:
        row2 = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task2.id))
        assert row2 is not None
        row2.next_run_at = now - timedelta(seconds=1)
        row2.schedule = {
            "run_at": (now - timedelta(minutes=5)).astimezone(UTC).isoformat(),
            "interval_minutes": None,
            "occurrence_limit": None,
            "idempotency_payload_hash": row2.schedule.get("idempotency_payload_hash"),
        }
        await database_session.commit()

    assert await scheduler.tick(now) == 1
    assert len(executor.invocations) == 2

    async with database.session() as database_session:
        row2_after = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task2.id))
        run2 = await database_session.scalar(select(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task2.id))
    assert row2_after is not None and row2_after.state == "completed"
    assert run2 is not None and run2.state == "completed" and run2.outcome_code == "succeeded"

