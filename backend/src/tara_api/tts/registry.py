"""Bounded, process-local FIFO registry for final-only TTS work."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from tara_api.domain.tts import (
    SpeechSynthesisError,
    SpeechSynthesisFailure,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechSynthesisState,
    SynthesisRequestIdentity,
    SynthesisRequestRecord,
)

SynthesisLifecycleListener = Callable[[SynthesisRequestIdentity, SpeechSynthesisState], Awaitable[None]]

_TERMINAL = frozenset({SpeechSynthesisState.COMPLETED, SpeechSynthesisState.CANCELED, SpeechSynthesisState.TIMED_OUT, SpeechSynthesisState.FAILED})
_ACTIVE = frozenset({SpeechSynthesisState.PREPARING, SpeechSynthesisState.SYNTHESIZING, SpeechSynthesisState.CHUNKING})
_ALLOWED = {
    SpeechSynthesisState.QUEUED: {SpeechSynthesisState.PREPARING, SpeechSynthesisState.CANCELED, SpeechSynthesisState.FAILED},
    SpeechSynthesisState.PREPARING: {SpeechSynthesisState.SYNTHESIZING, SpeechSynthesisState.CANCELED, SpeechSynthesisState.TIMED_OUT, SpeechSynthesisState.FAILED},
    SpeechSynthesisState.SYNTHESIZING: {SpeechSynthesisState.CHUNKING, SpeechSynthesisState.CANCELED, SpeechSynthesisState.TIMED_OUT, SpeechSynthesisState.FAILED},
    SpeechSynthesisState.CHUNKING: {SpeechSynthesisState.COMPLETED, SpeechSynthesisState.CANCELED, SpeechSynthesisState.TIMED_OUT, SpeechSynthesisState.FAILED},
}


@dataclass(frozen=True, slots=True)
class SynthesisRequestHandle:
    identity: SynthesisRequestIdentity
    completion: asyncio.Future[SynthesisRequestRecord]
    created: bool


@dataclass(slots=True)
class SynthesisJob:
    identity: SynthesisRequestIdentity
    provider_request: SpeechSynthesisRequest | None
    state: SpeechSynthesisState = SpeechSynthesisState.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completion: asyncio.Future[SynthesisRequestRecord] | None = None
    operation: Callable[[SynthesisJob], Awaitable[SpeechSynthesisResult]] | None = None
    execution_task: asyncio.Future[SpeechSynthesisResult] | None = None
    audio: SpeechSynthesisResult | None = None
    error: SpeechSynthesisError | None = None
    listener: SynthesisLifecycleListener | None = None


class SynthesisRequestRegistry:
    """FIFO worker queue with bounded records and transient process-local audio retention."""

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
        maximum_retained_audio_bytes: int,
    ) -> None:
        limits = (maximum_queued, maximum_concurrent, maximum_per_connection, maximum_per_session, maximum_per_owner, maximum_terminal_records, maximum_retained_audio_bytes)
        if min(limits) < 1 or maximum_concurrent > maximum_queued or terminal_retention.total_seconds() <= 0:
            raise ValueError("invalid TTS registry limits")
        self._maximum_queued = maximum_queued
        self._maximum_concurrent = maximum_concurrent
        self._maximum_per_connection = maximum_per_connection
        self._maximum_per_session = maximum_per_session
        self._maximum_per_owner = maximum_per_owner
        self._maximum_terminal_records = maximum_terminal_records
        self._terminal_retention = terminal_retention
        self._maximum_retained_audio_bytes = maximum_retained_audio_bytes
        self._retained_audio_bytes = 0
        self._jobs: dict[UUID, SynthesisJob] = {}
        self._idempotency: dict[tuple[UUID, UUID, str], UUID] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue(maxsize=maximum_queued)
        self._workers: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()

    async def begin(
        self,
        identity: SynthesisRequestIdentity,
        provider_request: SpeechSynthesisRequest,
        operation: Callable[[SynthesisJob], Awaitable[SpeechSynthesisResult]],
        *,
        listener: SynthesisLifecycleListener | None = None,
    ) -> SynthesisRequestHandle:
        async with self._lock:
            self._prune_locked(datetime.now(UTC))
            existing_id = self._idempotency.get(self._key(identity))
            if existing_id is not None and (existing := self._jobs.get(existing_id)) is not None and existing.completion is not None:
                return SynthesisRequestHandle(existing.identity, existing.completion, False)
            pending = tuple(job for job in self._jobs.values() if job.state not in _TERMINAL)
            self._check_limits(identity, pending)
            completion = asyncio.get_running_loop().create_future()
            job = SynthesisJob(identity, provider_request, completion=completion, operation=operation, listener=listener)
            self._jobs[identity.synthesis_request_id] = job
            self._idempotency[self._key(identity)] = identity.synthesis_request_id
            self._queue.put_nowait(identity.synthesis_request_id)
            self._ensure_workers_locked()
            return SynthesisRequestHandle(identity, completion, True)

    async def wait(self, handle: SynthesisRequestHandle) -> SynthesisRequestRecord:
        return await asyncio.shield(handle.completion)

    async def transition(self, request_id: UUID, target: SpeechSynthesisState) -> bool:
        notification: tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None = None
        async with self._lock:
            job = self._jobs.get(request_id)
            if job is None or job.state in _TERMINAL:
                return False
            if target not in _ALLOWED.get(job.state, set()):
                raise ValueError("invalid TTS state transition")
            job.state = target
            job.updated_at = datetime.now(UTC)
            if job.listener is not None:
                notification = job.listener, job.identity, target
        await self._notify(notification)
        return True

    async def consume_audio(self, request_id: UUID, *, owner_id: UUID, session_id: UUID, connection_id: UUID | None) -> SpeechSynthesisResult | None:
        async with self._lock:
            job = self._matching_job(request_id, owner_id, session_id, connection_id)
            if job is None or job.state != SpeechSynthesisState.COMPLETED:
                return None
            result, job.audio = job.audio, None
            if result is not None:
                self._retained_audio_bytes -= len(result.audio)
            return result

    async def cancel(self, request_id: UUID, *, owner_id: UUID, session_id: UUID, connection_id: UUID | None, error: SpeechSynthesisError = SpeechSynthesisError.REQUEST_CANCELED) -> bool:
        notification: tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None = None
        async with self._lock:
            job = self._matching_job(request_id, owner_id, session_id, connection_id)
            if job is None:
                return False
            if job.state in _TERMINAL:
                return job.state == SpeechSynthesisState.CANCELED
            notification = self._cancel_locked(job, error)
        await self._notify(notification)
        return True

    async def cancel_connection(self, connection_id: UUID) -> tuple[SynthesisRequestIdentity, ...]:
        return await self._cancel_matching(lambda job: job.identity.connection_id == connection_id, SpeechSynthesisError.REQUEST_CANCELED)

    async def cancel_session(self, owner_id: UUID, session_id: UUID) -> tuple[SynthesisRequestIdentity, ...]:
        return await self._cancel_matching(lambda job: (job.identity.owner_id, job.identity.session_id) == (owner_id, session_id), SpeechSynthesisError.SESSION_INVALIDATED)

    async def cleanup(self) -> None:
        async with self._lock:
            self._prune_locked(datetime.now(UTC))

    async def shutdown(self) -> None:
        async with self._lock:
            for job in self._jobs.values():
                if job.state not in _TERMINAL:
                    self._cancel_locked(job, SpeechSynthesisError.REQUEST_CANCELED)
                self._release_audio_locked(job)
            workers, self._workers = self._workers, []
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def counts(self) -> tuple[int, int, int, int]:
        async with self._lock:
            return (
                sum(job.state == SpeechSynthesisState.QUEUED for job in self._jobs.values()),
                sum(job.state in _ACTIVE for job in self._jobs.values()),
                sum(job.state in _TERMINAL for job in self._jobs.values()),
                self._retained_audio_bytes,
            )

    def _ensure_workers_locked(self) -> None:
        if not self._workers:
            self._workers = [asyncio.create_task(self._worker()) for _ in range(self._maximum_concurrent)]

    async def _worker(self) -> None:
        while True:
            request_id = await self._queue.get()
            try:
                async with self._lock:
                    job = self._jobs.get(request_id)
                    if job is None or job.state != SpeechSynthesisState.QUEUED or job.operation is None:
                        continue
                    job.execution_task = asyncio.ensure_future(job.operation(job))
                try:
                    result = await job.execution_task
                except asyncio.CancelledError:
                    worker = asyncio.current_task()
                    if worker is not None and worker.cancelling():
                        raise
                except SpeechSynthesisFailure as error:
                    state = SpeechSynthesisState.TIMED_OUT if error.code in {SpeechSynthesisError.PROVIDER_TIMEOUT, SpeechSynthesisError.REQUEST_TIMED_OUT} else SpeechSynthesisState.FAILED
                    await self._finish(job, state, error.code)
                except Exception:
                    await self._finish(job, SpeechSynthesisState.FAILED, SpeechSynthesisError.INTERNAL_TTS_ERROR)
                else:
                    await self._complete(job, result)
            finally:
                self._queue.task_done()

    async def _complete(self, job: SynthesisJob, result: SpeechSynthesisResult) -> None:
        notification: tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None = None
        async with self._lock:
            if job.state in _TERMINAL:
                return
            if job.state != SpeechSynthesisState.CHUNKING:
                notification = self._finish_locked(job, SpeechSynthesisState.FAILED, SpeechSynthesisError.INTERNAL_TTS_ERROR)
            else:
                self._evict_audio_locked(required=len(result.audio))
                if self._retained_audio_bytes + len(result.audio) > self._maximum_retained_audio_bytes:
                    notification = self._finish_locked(job, SpeechSynthesisState.FAILED, SpeechSynthesisError.RETAINED_AUDIO_LIMIT)
                else:
                    job.audio = result
                    self._retained_audio_bytes += len(result.audio)
                    job.provider_request = None
                    notification = self._finish_locked(job, SpeechSynthesisState.COMPLETED, None)
        await self._notify(notification)

    async def _finish(self, job: SynthesisJob, state: SpeechSynthesisState, error: SpeechSynthesisError) -> None:
        notification: tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None = None
        async with self._lock:
            if job.state not in _TERMINAL:
                notification = self._finish_locked(job, state, error)
        await self._notify(notification)

    async def _cancel_matching(self, predicate: Callable[[SynthesisJob], bool], error: SpeechSynthesisError) -> tuple[SynthesisRequestIdentity, ...]:
        notifications: list[tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None] = []
        async with self._lock:
            identities = []
            for job in self._jobs.values():
                if predicate(job) and job.state not in _TERMINAL:
                    identities.append(job.identity)
                    notifications.append(self._cancel_locked(job, error))
        for notification in notifications:
            await self._notify(notification)
        return tuple(identities)

    def _cancel_locked(self, job: SynthesisJob, error: SpeechSynthesisError) -> tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None:
        if job.execution_task is not None:
            job.execution_task.cancel()
        self._release_audio_locked(job)
        return self._finish_locked(job, SpeechSynthesisState.CANCELED, error)

    def _finish_locked(self, job: SynthesisJob, state: SpeechSynthesisState, error: SpeechSynthesisError | None) -> tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None:
        job.state = state
        job.error = error
        job.updated_at = datetime.now(UTC)
        job.provider_request = None
        if job.completion is not None and not job.completion.done():
            job.completion.set_result(self._record(job))
        return (job.listener, job.identity, state) if job.listener is not None else None

    @staticmethod
    async def _notify(notification: tuple[SynthesisLifecycleListener, SynthesisRequestIdentity, SpeechSynthesisState] | None) -> None:
        if notification is None:
            return
        listener, identity, state = notification
        try:
            await listener(identity, state)
        except Exception:
            return

    def _record(self, job: SynthesisJob) -> SynthesisRequestRecord:
        audio = job.audio
        return SynthesisRequestRecord(
            job.identity,
            job.state,
            job.updated_at,
            job.error,
            len(audio.audio) if audio else 0,
            len(audio.chunks) if audio else 0,
            audio.timing.audio_duration_ms if audio else None,
        )

    def _matching_job(self, request_id: UUID, owner_id: UUID, session_id: UUID, connection_id: UUID | None) -> SynthesisJob | None:
        job = self._jobs.get(request_id)
        if job is None or (job.identity.owner_id, job.identity.session_id, job.identity.connection_id) != (owner_id, session_id, connection_id):
            return None
        return job

    def _check_limits(self, identity: SynthesisRequestIdentity, pending: tuple[SynthesisJob, ...]) -> None:
        if sum(job.state == SpeechSynthesisState.QUEUED for job in pending) >= self._maximum_queued:
            raise ValueError(SpeechSynthesisError.QUEUE_FULL.value)
        if identity.connection_id is not None and sum(job.identity.connection_id == identity.connection_id for job in pending) >= self._maximum_per_connection:
            raise ValueError(SpeechSynthesisError.CONNECTION_REQUEST_LIMIT.value)
        if sum(job.identity.session_id == identity.session_id for job in pending) >= self._maximum_per_session:
            raise ValueError(SpeechSynthesisError.SESSION_REQUEST_LIMIT.value)
        if sum(job.identity.owner_id == identity.owner_id for job in pending) >= self._maximum_per_owner:
            raise ValueError(SpeechSynthesisError.OWNER_REQUEST_LIMIT.value)

    @staticmethod
    def _key(identity: SynthesisRequestIdentity) -> tuple[UUID, UUID, str]:
        return identity.owner_id, identity.session_id, identity.idempotency_key_hash

    def _release_audio_locked(self, job: SynthesisJob) -> None:
        if job.audio is not None:
            self._retained_audio_bytes -= len(job.audio.audio)
            job.audio = None

    def _evict_audio_locked(self, *, required: int) -> None:
        completed = sorted((job for job in self._jobs.values() if job.audio is not None), key=lambda job: job.updated_at)
        for job in completed:
            if self._retained_audio_bytes + required <= self._maximum_retained_audio_bytes:
                return
            self._release_audio_locked(job)

    def _prune_locked(self, now: datetime) -> None:
        terminal = sorted((job for job in self._jobs.values() if job.state in _TERMINAL), key=lambda job: job.updated_at)
        expired = [job for job in terminal if job.updated_at + self._terminal_retention <= now]
        excess = terminal[: max(0, len(terminal) - self._maximum_terminal_records)]
        for job in {job.identity.synthesis_request_id: job for job in (*expired, *excess)}.values():
            self._release_audio_locked(job)
            self._jobs.pop(job.identity.synthesis_request_id, None)
            self._idempotency.pop(self._key(job.identity), None)
