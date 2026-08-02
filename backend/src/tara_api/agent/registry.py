"""Bounded, process-local FIFO agent request registry for M9C."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from tara_api.domain.agent import AgentError, AgentRequest, AgentResponse, AgentState

_TERMINAL = frozenset({AgentState.COMPLETED, AgentState.CANCELED, AgentState.TIMED_OUT, AgentState.FAILED})
_ALLOWED = {
    AgentState.QUEUED: {AgentState.ROUTING, AgentState.CANCELED, AgentState.FAILED},
    AgentState.ROUTING: {AgentState.RETRIEVING_CONTEXT, AgentState.COMPLETED, AgentState.CANCELED, AgentState.FAILED},
    AgentState.RETRIEVING_CONTEXT: {AgentState.GENERATING, AgentState.CANCELED, AgentState.FAILED},
    AgentState.GENERATING: {AgentState.COMPLETED, AgentState.CANCELED, AgentState.TIMED_OUT, AgentState.FAILED},
    AgentState.WAITING_FOR_CONFIRMATION: {AgentState.CANCELED, AgentState.FAILED},
}

AgentLifecycleListener = Callable[[AgentRequest, AgentState], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AgentRequestHandle:
    """Accepted process-local request and its single completion future."""

    request: AgentRequest
    completion: asyncio.Future[AgentResponse]
    created: bool


@dataclass(slots=True)
class AgentJob:
    request: AgentRequest
    state: AgentState = AgentState.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    result: asyncio.Future[AgentResponse] | None = None
    execution_task: asyncio.Future[AgentResponse] | None = None
    operation: Callable[[AgentJob], Awaitable[AgentResponse]] | None = None
    listener: AgentLifecycleListener | None = None


class AgentRequestRegistry:
    """FIFO worker queue with bounded records; unsuitable for multi-process deployment."""

    def __init__(
        self,
        *,
        maximum_queued: int,
        maximum_concurrent: int,
        maximum_per_connection: int,
        maximum_per_session: int,
        maximum_per_owner: int,
        maximum_terminal_records: int,
        terminal_retention: timedelta,
    ) -> None:
        if min(maximum_queued, maximum_concurrent, maximum_per_connection, maximum_per_session, maximum_per_owner, maximum_terminal_records) < 1 or terminal_retention.total_seconds() <= 0:
            raise ValueError("invalid agent registry limits")
        self._maximum_queued = maximum_queued
        self._maximum_concurrent = maximum_concurrent
        self._maximum_per_connection = maximum_per_connection
        self._maximum_per_session = maximum_per_session
        self._maximum_per_owner = maximum_per_owner
        self._maximum_terminal_records = maximum_terminal_records
        self._terminal_retention = terminal_retention
        self._jobs: dict[UUID, AgentJob] = {}
        self._idempotency: dict[tuple[UUID, UUID, str], UUID] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue(maxsize=maximum_queued)
        self._workers: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()

    async def begin(
        self,
        request: AgentRequest,
        operation: Callable[[AgentJob], Awaitable[AgentResponse]],
        *,
        listener: AgentLifecycleListener | None = None,
    ) -> AgentRequestHandle:
        key = self._key(request)
        async with self._lock:
            self._prune_locked(datetime.now(UTC))
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                existing = self._jobs.get(existing_id)
                if existing is not None and existing.result is not None:
                    if existing.request.connection_id != request.connection_id:
                        raise ValueError(AgentError.DUPLICATE_REQUEST.value)
                    return AgentRequestHandle(existing.request, existing.result, False)
                else:
                    raise ValueError(AgentError.DUPLICATE_REQUEST.value)
            pending = tuple(job for job in self._jobs.values() if job.state not in _TERMINAL)
            self._check_limits(request, pending)
            completion = asyncio.get_running_loop().create_future()
            job = AgentJob(request=request, result=completion, operation=operation, listener=listener)
            self._jobs[request.request_id] = job
            self._idempotency[key] = request.request_id
            self._queue.put_nowait(request.request_id)
            self._ensure_workers_locked()
            return AgentRequestHandle(request, completion, True)

    async def submit(self, request: AgentRequest, operation: Callable[[AgentJob], Awaitable[AgentResponse]]) -> AgentResponse:
        return await self.wait(await self.begin(request, operation))

    @staticmethod
    async def wait(handle: AgentRequestHandle) -> AgentResponse:
        return await asyncio.shield(handle.completion)

    async def transition(self, request_id: UUID, target: AgentState) -> bool:
        notification: tuple[AgentLifecycleListener, AgentRequest, AgentState] | None = None
        async with self._lock:
            job = self._jobs.get(request_id)
            if job is None or job.state in _TERMINAL:
                return False
            if target not in _ALLOWED.get(job.state, set()):
                raise ValueError(AgentError.INVALID_REQUEST_STATE.value)
            job.state = target
            job.updated_at = datetime.now(UTC)
            if job.listener is not None:
                notification = job.listener, job.request, target
        await self._notify(notification)
        return True

    async def cancel(self, request_id: UUID, owner_id: UUID, session_id: UUID, connection_id: UUID | None) -> bool:
        notification: tuple[AgentLifecycleListener, AgentRequest, AgentState] | None = None
        async with self._lock:
            job = self._jobs.get(request_id)
            if job is None or (job.request.owner_id, job.request.session_id, job.request.connection_id) != (owner_id, session_id, connection_id):
                return False
            if job.state in _TERMINAL:
                return job.state == AgentState.CANCELED
            notification = self._cancel_locked(job, AgentError.REQUEST_CANCELED)
        await self._notify(notification)
        return True

    async def cancel_connection(self, connection_id: UUID) -> tuple[AgentRequest, ...]:
        return await self._cancel_matching(lambda job: job.request.connection_id == connection_id, AgentError.REQUEST_CANCELED)

    async def cancel_session(self, owner_id: UUID, session_id: UUID, error: AgentError = AgentError.SESSION_INVALIDATED) -> tuple[AgentRequest, ...]:
        return await self._cancel_matching(lambda job: (job.request.owner_id, job.request.session_id) == (owner_id, session_id), error)

    async def cleanup(self) -> None:
        async with self._lock:
            self._prune_locked(datetime.now(UTC))

    async def shutdown(self) -> None:
        notifications: list[tuple[AgentLifecycleListener, AgentRequest, AgentState] | None] = []
        async with self._lock:
            for job in self._jobs.values():
                if job.state not in _TERMINAL:
                    notifications.append(self._cancel_locked(job, AgentError.REQUEST_CANCELED))
            workers, self._workers = self._workers, []
        for notification in notifications:
            await self._notify(notification)
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def counts(self) -> tuple[int, int, int]:
        async with self._lock:
            queued = sum(job.state == AgentState.QUEUED for job in self._jobs.values())
            active = sum(job.state in {AgentState.ROUTING, AgentState.RETRIEVING_CONTEXT, AgentState.GENERATING} for job in self._jobs.values())
            terminal = sum(job.state in _TERMINAL for job in self._jobs.values())
            return queued, active, terminal

    async def get_request(self, request_id: UUID, owner_id: UUID, session_id: UUID, connection_id: UUID | None) -> AgentRequest | None:
        async with self._lock:
            job = self._jobs.get(request_id)
            if job is None or (job.request.owner_id, job.request.session_id, job.request.connection_id) != (owner_id, session_id, connection_id):
                return None
            return job.request

    def _ensure_workers_locked(self) -> None:
        if self._workers:
            return
        self._workers = [asyncio.create_task(self._worker()) for _ in range(self._maximum_concurrent)]

    async def _worker(self) -> None:
        while True:
            request_id = await self._queue.get()
            try:
                async with self._lock:
                    job = self._jobs.get(request_id)
                    if job is None or job.state != AgentState.QUEUED or job.operation is None:
                        continue
                    operation = job.operation
                    job.execution_task = asyncio.ensure_future(operation(job))
                try:
                    response = await job.execution_task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
                    continue
                except Exception:
                    await self._fail(job, AgentError.INTERNAL_AGENT_ERROR)
                else:
                    await self._complete(job, response)
            finally:
                self._queue.task_done()

    async def _complete(self, job: AgentJob, response: AgentResponse) -> None:
        notification: tuple[AgentLifecycleListener, AgentRequest, AgentState] | None = None
        async with self._lock:
            if job.state in _TERMINAL:
                return
            if response.state not in _TERMINAL:
                notification = self._cancel_locked(job, AgentError.INTERNAL_AGENT_ERROR)
            else:
                job.state = response.state
                job.updated_at = datetime.now(UTC)
                if job.result is not None and not job.result.done():
                    job.result.set_result(response)
                if job.listener is not None:
                    notification = job.listener, job.request, response.state
        await self._notify(notification)

    async def _fail(self, job: AgentJob, error: AgentError) -> None:
        notification: tuple[AgentLifecycleListener, AgentRequest, AgentState] | None = None
        async with self._lock:
            if job.state not in _TERMINAL:
                notification = self._finish_locked(job, AgentState.FAILED, error)
        await self._notify(notification)

    async def _cancel_matching(self, predicate: Callable[[AgentJob], bool], error: AgentError) -> tuple[AgentRequest, ...]:
        notifications: list[tuple[AgentLifecycleListener, AgentRequest, AgentState] | None] = []
        canceled: list[AgentRequest] = []
        async with self._lock:
            for job in self._jobs.values():
                if predicate(job) and job.state not in _TERMINAL:
                    canceled.append(job.request)
                    notifications.append(self._cancel_locked(job, error))
        for notification in notifications:
            await self._notify(notification)
        return tuple(canceled)

    def _cancel_locked(self, job: AgentJob, error: AgentError) -> tuple[AgentLifecycleListener, AgentRequest, AgentState] | None:
        if job.execution_task is not None:
            job.execution_task.cancel()
        return self._finish_locked(job, AgentState.CANCELED, error)

    def _finish_locked(self, job: AgentJob, state: AgentState, error: AgentError) -> tuple[AgentLifecycleListener, AgentRequest, AgentState] | None:
        job.state = state
        job.updated_at = datetime.now(UTC)
        if job.result is not None and not job.result.done():
            job.result.set_result(AgentResponse(job.request.request_id, "The request could not be completed.", state, job.updated_at, error))
        return (job.listener, job.request, state) if job.listener is not None else None

    @staticmethod
    async def _notify(notification: tuple[AgentLifecycleListener, AgentRequest, AgentState] | None) -> None:
        if notification is None:
            return
        listener, request, state = notification
        try:
            await listener(request, state)
        except Exception:
            return

    def _check_limits(self, request: AgentRequest, pending: tuple[AgentJob, ...]) -> None:
        if sum(job.state == AgentState.QUEUED for job in pending) >= self._maximum_queued:
            raise ValueError(AgentError.QUEUE_FULL.value)
        if request.connection_id is not None and sum(job.request.connection_id == request.connection_id for job in pending) >= self._maximum_per_connection:
            raise ValueError(AgentError.CONNECTION_REQUEST_LIMIT.value)
        if sum(job.request.session_id == request.session_id for job in pending) >= self._maximum_per_session:
            raise ValueError(AgentError.SESSION_REQUEST_LIMIT.value)
        if sum(job.request.owner_id == request.owner_id for job in pending) >= self._maximum_per_owner:
            raise ValueError(AgentError.OWNER_REQUEST_LIMIT.value)

    @staticmethod
    def _key(request: AgentRequest) -> tuple[UUID, UUID, str]:
        if request.idempotency_key_hash is None:
            raise ValueError("agent request lacks idempotency identity")
        return request.owner_id, request.session_id, request.idempotency_key_hash

    def _prune_locked(self, now: datetime) -> None:
        terminal = sorted(
            (job for job in self._jobs.values() if job.state in _TERMINAL),
            key=lambda job: job.updated_at,
        )
        expired = [job for job in terminal if job.updated_at + self._terminal_retention <= now]
        excess = terminal[: max(0, len(terminal) - self._maximum_terminal_records)]
        for job in {job.request.request_id: job for job in (*expired, *excess)}.values():
            self._jobs.pop(job.request.request_id, None)
            self._idempotency.pop(self._key(job.request), None)
