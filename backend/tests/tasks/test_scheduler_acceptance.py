"""Deterministic scheduler runtime acceptance tests for M16 Part A."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.models import (
    ToolRequest,
    ToolResult,
    ToolResultStatus,
)
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.persistence.models import (
    ScheduledTaskModel,
    ScheduledTaskRunModel,
)
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.safety.clock import SystemClock
from tara_api.safety.confirmations import DeterministicConfirmationService
from tara_api.safety.policy import DeterministicActionPolicyService
from tara_api.tasks.payloads import TaskPayloadProtector
from tara_api.tasks.scheduler import ScheduledTaskScheduler
from tara_api.tasks.service import ScheduledTaskService


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


class _CountingExecutor:
    def __init__(self, status: ToolResultStatus = ToolResultStatus.SUCCEEDED) -> None:
        self.invocations = 0
        self.status = status

    async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
        self.invocations += 1
        return ToolResult(self.status, "counting result")


class _EventControllableExecutor:
    def __init__(self, status: ToolResultStatus = ToolResultStatus.SUCCEEDED) -> None:
        self.started_event = asyncio.Event()
        self.release_event = asyncio.Event()
        self.invocations = 0
        self.status = status

    async def execute(self, _request: ToolRequest, authorization: object | None = None) -> ToolResult:
        self.invocations += 1
        self.started_event.set()
        await self.release_event.wait()
        return ToolResult(self.status, "event result")


# ============================================================================
# Section 1: Timeout correctness
# ============================================================================


async def test_timeout_prevents_late_success_overwrite_and_releases_permits(
    database: Database,
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
        DeterministicConfirmationService(SqlAlchemySafetyStore(database), SystemClock(), context_validator=authentication),
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
    )

    task = await service.create(context, _command(idempotency_key="timeout-late-success"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    executor = _EventControllableExecutor()
    scheduler = ScheduledTaskScheduler(
        database,
        registry,
        executor,
        TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="),
        maximum_concurrency=2,
        maximum_per_owner=1,
        run_timeout_seconds=1,
    )
    scheduler._run_timeout_seconds = 0.05

    tick_task = asyncio.create_task(scheduler.tick(now))
    await executor.started_event.wait()
    await tick_task

    # Task timed out. Release executor for late completion.
    executor.release_event.set()
    await asyncio.sleep(0.01)

    async with database.session() as database_session:
        row_after = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        runs = list((await database_session.scalars(select(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task.id))).all())

    assert row_after is not None
    assert row_after.state == "failed"
    assert row_after.enabled is False
    assert row_after.claim_id is None
    assert row_after.next_run_at is None
    assert row_after.last_outcome == "task_execution_timed_out"
    assert len(runs) == 1
    assert runs[0].state == "failed"
    assert runs[0].error_code == "task_execution_timed_out"

    # Permits & limiters must be released
    assert scheduler._global._value == 2  # noqa: SLF001
    assert context.owner.id not in scheduler._owner_limits  # noqa: SLF001

    # Later task executes successfully
    task2 = await service.create(context, _command(idempotency_key="task2-after-timeout"))
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

    executor2 = _CountingExecutor()
    scheduler2 = ScheduledTaskScheduler(database, registry, executor2, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    assert await scheduler2.tick(now) == 1
    assert executor2.invocations == 1


async def test_uncertain_external_outcome_recorded_properly(database: Database, tmp_path: Path) -> None:
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

    task = await service.create(context, _command(idempotency_key="uncertain-outcome"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        row.schedule = {
            "run_at": (now - timedelta(minutes=5)).astimezone(UTC).isoformat(),
            "interval_minutes": None,
            "occurrence_limit": None,
            "idempotency_payload_hash": row.schedule.get("idempotency_payload_hash"),
        }
        await database_session.commit()

    executor = _CountingExecutor(status=ToolResultStatus.UNCERTAIN)
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    assert await scheduler.tick(now) == 1
    assert executor.invocations == 1

    async with database.session() as database_session:
        row_after = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        run = await database_session.scalar(select(ScheduledTaskRunModel).where(ScheduledTaskRunModel.task_id == task.id))

    assert row_after is not None
    assert row_after.last_outcome == "uncertain"
    assert run is not None and run.state == "completed" and run.outcome_code == "uncertain"


# ============================================================================
# Section 2: Cancellation correctness
# ============================================================================


async def test_cancellation_unrelated_task_continues(database: Database, tmp_path: Path) -> None:
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

    task1 = await service.create(context, _command(idempotency_key="cancel-task1"))
    task2 = await service.create(context, _command(idempotency_key="continue-task2"))
    now = datetime.now(UTC)

    async with database.session() as database_session:
        for t in (task1, task2):
            r = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == t.id))
            assert r is not None
            r.next_run_at = now - timedelta(seconds=1)
            r.schedule = {
                "run_at": (now - timedelta(minutes=5)).astimezone(UTC).isoformat(),
                "interval_minutes": None,
                "occurrence_limit": None,
                "idempotency_payload_hash": r.schedule.get("idempotency_payload_hash"),
            }
        await database_session.commit()

    # Cancel task1 before poll
    await service.cancel(context, task1.id)

    executor = _CountingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    assert await scheduler.tick(now) == 1
    assert executor.invocations == 1

    async with database.session() as database_session:
        r1 = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task1.id))
        r2 = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task2.id))

    assert r1 is not None and r1.state == "canceled"
    assert r2 is not None and r2.state == "completed"


# ============================================================================
# Section 3: Final claim-to-execution revalidation
# ============================================================================


async def test_revalidation_boundaries_prevent_capability_invocation(database: Database, tmp_path: Path) -> None:
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

    # Test cases for mutations applied after claim
    mutations: list[tuple[str, Any]] = [
        ("cancel", lambda s, t: s.cancel(context, t.id)),
        ("pause", lambda s, t: s.pause(context, t.id)),
        ("disable", lambda s, t: s.disable(context, t.id)),
        ("delete", lambda s, t: s.delete(context, t.id)),
    ]

    for key, mutate in mutations:
        task = await service.create(context, _command(idempotency_key=f"reval-{key}"))
        async with database.session() as database_session:
            row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
            assert row is not None
            row.next_run_at = now - timedelta(seconds=1)
            await database_session.commit()

        async with database.unit_of_work() as unit:
            claimed = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
            assert len(claimed) == 1

        # Apply mutation
        await mutate(service, task)

        executor = _CountingExecutor()
        scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
        await scheduler._process(claimed[0][0], claimed[0][1], now)  # noqa: SLF001

        assert executor.invocations == 0, f"Executor invoked for {key}"
        assert scheduler._global._value == 2  # noqa: SLF001
        assert context.owner.id not in scheduler._owner_limits  # noqa: SLF001


# ============================================================================
# Section 4: Completion, cancellation, timeout, and deletion races
# ============================================================================


async def test_claim_versus_delete_race(database: Database, tmp_path: Path) -> None:
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

    task = await service.create(context, _command(idempotency_key="race-delete"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    async with database.unit_of_work() as unit:
        claimed = await unit.scheduled_tasks.claim_due(now, 1, timedelta(seconds=60))
        assert len(claimed) == 1

    # Delete task right after claim
    assert await service.delete(context, task.id) is True

    executor = _CountingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))
    await scheduler._process(claimed[0][0], claimed[0][1], now)  # noqa: SLF001

    assert executor.invocations == 0
    async with database.session() as database_session:
        deleted_row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
    assert deleted_row is None


# ============================================================================
# Section 5: Polling and claim acceptance
# ============================================================================


async def test_concurrent_ticks_claim_due_tasks_without_duplicates(database: Database, tmp_path: Path) -> None:
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

    task = await service.create(context, _command(idempotency_key="concurrent-ticks"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        await database_session.commit()

    executor = _CountingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    # Run 10 concurrent ticks against the same scheduler
    results = await asyncio.gather(*(scheduler.tick(now) for _ in range(10)))

    assert sum(results) == 1
    assert executor.invocations == 1


# ============================================================================
# Section 6: Per-owner concurrency acceptance
# ============================================================================


async def test_owner_limiter_map_cleanup_after_many_owners(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    executor = _CountingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    # Retain and release limiters for 100 foreign owner IDs
    for _ in range(100):
        fake_owner_id = uuid4()
        limiter = await scheduler._retain_owner_limit(fake_owner_id)  # noqa: SLF001
        await scheduler._release_owner_limit(fake_owner_id, limiter)  # noqa: SLF001

    assert len(scheduler._owner_limits) == 0  # noqa: SLF001


# ============================================================================
# Section 7: Shutdown acceptance
# ============================================================================


async def test_scheduler_start_stop_idempotency_and_shutdown_lifecycle(database: Database, tmp_path: Path) -> None:
    context, authentication = await _authenticated_context(database)
    root = tmp_path / "root"
    root.mkdir()
    registry = CapabilityRegistry(AllowlistedFilesystemListTool((root,)))
    executor = _CountingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="), poll_seconds=0.1)

    # Start twice
    scheduler.start()
    assert scheduler._loop_task is not None and not scheduler._loop_task.done()  # noqa: SLF001
    task_ref = scheduler._loop_task  # noqa: SLF001
    scheduler.start()
    assert scheduler._loop_task is task_ref  # noqa: SLF001

    # Stop twice
    await scheduler.stop()
    assert scheduler._loop_task is None  # noqa: SLF001
    await scheduler.stop()
    assert scheduler._loop_task is None  # noqa: SLF001


# ============================================================================
# Section 8: Cleanup failure isolation
# ============================================================================


async def test_cleanup_failure_does_not_break_scheduler_polling(database: Database, tmp_path: Path) -> None:
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

    task = await service.create(context, _command(idempotency_key="cleanup-failure-isolation"))
    now = datetime.now(UTC)
    async with database.session() as database_session:
        row = await database_session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task.id))
        assert row is not None
        row.next_run_at = now - timedelta(seconds=1)
        row.schedule = {
            "run_at": (now - timedelta(minutes=5)).astimezone(UTC).isoformat(),
            "interval_minutes": None,
            "occurrence_limit": None,
            "idempotency_payload_hash": row.schedule.get("idempotency_payload_hash"),
        }
        await database_session.commit()

    executor = _CountingExecutor()
    scheduler = ScheduledTaskScheduler(database, registry, executor, TaskPayloadProtector("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="))

    # Mock cleanup to fail
    async def failing_cleanup(_now: datetime | None = None) -> tuple[int, int]:
        raise RuntimeError("database cleanup failure")

    scheduler.cleanup = failing_cleanup  # type: ignore[assignment]

    # Polling still works
    assert await scheduler.tick(now) == 1
    assert executor.invocations == 1
