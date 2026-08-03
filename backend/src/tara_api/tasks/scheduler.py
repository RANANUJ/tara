"""Bounded process-local scheduled-task claiming with fail-closed execution."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from tara_api.domain.models import JsonValue, ToolRequest, ToolResultStatus
from tara_api.domain.protocols import ToolExecutor, ToolRegistry
from tara_api.domain.tasks import ScheduleDefinition
from tara_api.persistence.database import Database
from tara_api.persistence.models import ScheduledTaskModel
from tara_api.tasks.payloads import TaskPayloadProtector, UnavailableTaskPayloadProtector


class ScheduledTaskScheduler:
    """Poll and atomically claim due tasks without reconstructing private inputs."""

    def __init__(
        self,
        database: Database,
        registry: ToolRegistry,
        executor: ToolExecutor,
        payload_protector: TaskPayloadProtector | UnavailableTaskPayloadProtector,
        *,
        poll_seconds: float = 5,
        due_batch_size: int = 8,
        maximum_concurrency: int = 2,
        maximum_per_owner: int = 1,
        claim_lease_seconds: int = 60,
        run_timeout_seconds: int = 30,
        cleanup_interval_seconds: int = 300,
        cleanup_batch_size: int = 32,
        payload_retention_hours: int = 24,
        run_retention_days: int = 30,
    ) -> None:
        if not 1 <= due_batch_size <= 64 or not 1 <= maximum_concurrency <= 8:
            raise ValueError("invalid_scheduler_limits")
        if not 1 <= maximum_per_owner <= maximum_concurrency or not 1 <= claim_lease_seconds <= 300 or not 1 <= run_timeout_seconds <= 300:
            raise ValueError("invalid_scheduler_limits")
        if not 0.1 <= poll_seconds <= 300:
            raise ValueError("invalid_scheduler_poll_interval")
        self._database = database
        self._registry = registry
        self._executor = executor
        self._payload_protector = payload_protector
        self._poll_seconds = poll_seconds
        self._due_batch_size = due_batch_size
        self._lease = timedelta(seconds=claim_lease_seconds)
        self._run_timeout_seconds = run_timeout_seconds
        self._cleanup_interval = timedelta(seconds=cleanup_interval_seconds)
        self._cleanup_batch_size = cleanup_batch_size
        self._payload_retention = timedelta(hours=payload_retention_hours)
        self._run_retention = timedelta(days=run_retention_days)
        self._last_cleanup_at: datetime | None = None
        self._global = asyncio.Semaphore(maximum_concurrency)
        self._owner_limits: dict[UUID, asyncio.Semaphore] = {}
        self._maximum_per_owner = maximum_per_owner
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._stopping = False
            self._loop_task = asyncio.create_task(self._run(), name="tara-scheduled-task-poller")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        self._loop_task = None

    async def tick(self, now: datetime | None = None) -> int:
        claimed_at = now or datetime.now(UTC)
        async with self._database.unit_of_work() as unit:
            await unit.scheduled_tasks.recover_stale_claims(claimed_at, self._due_batch_size)
            claimed = await unit.scheduled_tasks.claim_due(claimed_at, self._due_batch_size, self._lease)
        await asyncio.gather(*(self._process(task, run_id, claimed_at) for task, run_id in claimed))
        return len(claimed)

    async def _run(self) -> None:
        while not self._stopping:
            now = datetime.now(UTC)
            await self.tick(now)
            if self._last_cleanup_at is None or now - self._last_cleanup_at >= self._cleanup_interval:
                with suppress(Exception):
                    await self.cleanup(now)
            await asyncio.sleep(self._poll_seconds)

    async def cleanup(self, now: datetime | None = None) -> tuple[int, int]:
        current = now or datetime.now(UTC)
        async with self._database.unit_of_work() as unit:
            payloads = await unit.scheduled_tasks.cleanup_payloads(current - self._payload_retention, self._cleanup_batch_size)
            if payloads < self._cleanup_batch_size:
                payloads += await unit.scheduled_tasks.cleanup_completed_payloads(
                    current - self._payload_retention,
                    self._cleanup_batch_size - payloads,
                )
            runs = await unit.scheduled_tasks.cleanup_runs(current - self._run_retention, self._cleanup_batch_size)
        self._last_cleanup_at = current
        return payloads, runs

    async def _process(self, task: ScheduledTaskModel, run_id: UUID, now: datetime) -> None:
        owner = self._owner_limits.setdefault(task.owner_id, asyncio.Semaphore(self._maximum_per_owner))
        async with self._global, owner:
            try:
                async with self._database.unit_of_work() as unit:
                    payload = await unit.scheduled_tasks.get_active_payload(task.id, task.owner_id, now)
                    if payload is None or payload.capability_id != task.capability_id or payload.binding_hash != task.confirmation_binding_hash:
                        raise ValueError("task_payload_unavailable")
                    target, parameters = self._payload_protector.reveal(
                        task_id=task.id, owner_id=task.owner_id, capability_id=payload.capability_id, binding_hash=payload.binding_hash,
                        payload_version=payload.payload_version, nonce=payload.nonce, ciphertext=payload.ciphertext,
                    )
                    tool = self._registry.get(payload.capability_id)
                    if tool is None:
                        raise ValueError("task_capability_unavailable")
                    arguments = {"target": target, **parameters}
                    tool.validate_arguments(arguments)
                    if not await unit.scheduled_tasks.mark_running(task.id, run_id, now):
                        return
                result = await asyncio.wait_for(
                    self._executor.execute(ToolRequest(tool.definition.name, tool.definition.version, cast(dict[str, JsonValue], arguments))),
                    timeout=self._run_timeout_seconds,
                )
                if result.status not in {ToolResultStatus.SUCCEEDED, ToolResultStatus.UNCERTAIN}:
                    raise ValueError("task_execution_denied")
                schedule = ScheduleDefinition(task.timezone, datetime.fromisoformat(str(task.schedule["run_at"])), task.schedule.get("interval_minutes"), task.schedule.get("occurrence_limit"))
                next_run_at = schedule.next_after(now)
                async with self._database.unit_of_work() as unit:
                    await unit.scheduled_tasks.complete_claim(task.id, run_id, datetime.now(UTC), next_run_at, result.status.value)
            except ValueError as error:
                async with self._database.unit_of_work() as unit:
                    await unit.scheduled_tasks.fail_claim(task.id, run_id, datetime.now(UTC), str(error))
            except TimeoutError:
                async with self._database.unit_of_work() as unit:
                    await unit.scheduled_tasks.fail_claim(task.id, run_id, datetime.now(UTC), "task_execution_timed_out")
