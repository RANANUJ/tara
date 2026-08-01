"""Bounded, process-local STT jobs and deterministic provider fixtures."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from tara_api.domain.stt import FinalTranscript, PartialTranscript, SpeechToTextProvider, SpeechToTextSession, TranscriptionError, TranscriptionJob, TranscriptionJobRegistry, TranscriptionRequest, TranscriptionStatus, TranscriptLanguage


def pcm_sample_count(pcm16: bytes) -> int:
    if not pcm16 or len(pcm16) % 2:
        raise ValueError("invalid PCM16")
    return len(pcm16) // 2


def pcm_duration_ms(pcm16: bytes, sample_rate: int = 16000) -> int:
    return round(pcm_sample_count(pcm16) * 1000 / sample_rate)


class FakeSession:
    def __init__(self, outputs: tuple[PartialTranscript | FinalTranscript, ...]) -> None:
        self._outputs = outputs
        self._canceled = False

    def results(self) -> AsyncIterator[PartialTranscript | FinalTranscript]:
        return self._results()

    async def _results(self) -> AsyncIterator[PartialTranscript | FinalTranscript]:
        for output in self._outputs:
            if self._canceled:
                return
            yield output

    async def cancel(self) -> None:
        self._canceled = True


class FakeSpeechToTextProvider:
    name = "fake"

    def __init__(self, outputs: tuple[PartialTranscript | FinalTranscript, ...] | None = None) -> None:
        self._outputs = outputs or (FinalTranscript("test transcript", TranscriptLanguage("en")),)

    async def readiness(self) -> bool:
        return True

    async def start(self, _request: TranscriptionRequest) -> SpeechToTextSession:
        return FakeSession(self._outputs)


Publisher = Callable[[TranscriptionJob, str, dict[str, object]], Awaitable[None]]
TERMINAL_STATES = {TranscriptionStatus.COMPLETED, TranscriptionStatus.CANCELED, TranscriptionStatus.TIMED_OUT, TranscriptionStatus.FAILED}
ALLOWED_TRANSITIONS = {
    TranscriptionStatus.QUEUED: {TranscriptionStatus.PREPARING, TranscriptionStatus.CANCELED, TranscriptionStatus.FAILED},
    TranscriptionStatus.PREPARING: {TranscriptionStatus.TRANSCRIBING, TranscriptionStatus.CANCELED, TranscriptionStatus.TIMED_OUT, TranscriptionStatus.FAILED},
    TranscriptionStatus.TRANSCRIBING: {TranscriptionStatus.PARTIAL, TranscriptionStatus.COMPLETED, TranscriptionStatus.CANCELED, TranscriptionStatus.TIMED_OUT, TranscriptionStatus.FAILED},
    TranscriptionStatus.PARTIAL: {TranscriptionStatus.PARTIAL, TranscriptionStatus.COMPLETED, TranscriptionStatus.CANCELED, TranscriptionStatus.TIMED_OUT, TranscriptionStatus.FAILED},
}


class InMemoryTranscriptionJobs(TranscriptionJobRegistry):
    """Bounded process-local registry; it is not suitable for multi-process deployment."""

    def __init__(self, provider: SpeechToTextProvider, publish: Publisher, maximum_queued: int = 8, maximum_concurrent: int = 1, timeout_seconds: float = 30, maximum_per_connection: int = 2, maximum_per_session: int = 4, maximum_audio_bytes: int = 960000) -> None:  # noqa: E501
        self._provider = provider
        self._publish = publish
        self._maximum_queued = maximum_queued
        self._maximum_per_connection = maximum_per_connection
        self._maximum_per_session = maximum_per_session
        self._maximum_audio_bytes = maximum_audio_bytes
        self._timeout = timeout_seconds
        self._jobs: dict[UUID, TranscriptionJob] = {}
        self._turns: dict[tuple[UUID, UUID, UUID], UUID] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(maximum_concurrent)

    async def submit(self, request: TranscriptionRequest) -> TranscriptionJob:
        duration = pcm_duration_ms(request.pcm16)
        if duration < 40:
            raise ValueError(TranscriptionError.AUDIO_TOO_SHORT)
        if len(request.pcm16) > self._maximum_audio_bytes:
            raise ValueError("audio_too_long")
        key = (request.connection_id, request.audio_session_id, request.turn_id)
        async with self._lock:
            existing = self._turns.get(key)
            if existing is not None:
                return self._jobs[existing]
            pending = [job for job in self._jobs.values() if job.status not in TERMINAL_STATES]
            if len(pending) >= self._maximum_queued:
                raise ValueError(TranscriptionError.QUEUE_FULL)
            if sum(job.request.connection_id == request.connection_id for job in pending) >= self._maximum_per_connection:
                raise ValueError("connection_job_limit")
            if sum(job.request.session_id == request.session_id for job in pending) >= self._maximum_per_session:
                raise ValueError("session_job_limit")
            job = TranscriptionJob(request)
            self._jobs[request.transcription_id] = job
            self._turns[key] = request.transcription_id
            job.task = asyncio.create_task(self._run(job))
            return job

    async def get(self, transcription_id: UUID, owner_id: UUID, session_id: UUID, connection_id: UUID) -> TranscriptionJob | None:
        async with self._lock:
            job = self._jobs.get(transcription_id)
            if job is None or (job.request.owner_id, job.request.session_id, job.request.connection_id) != (owner_id, session_id, connection_id):
                return None
            return job

    async def cancel(self, transcription_id: UUID, connection_id: UUID, owner_id: UUID | None = None, session_id: UUID | None = None) -> bool:
        async with self._lock:
            job = self._jobs.get(transcription_id)
            if job is None or job.request.connection_id != connection_id or owner_id is not None and job.request.owner_id != owner_id or session_id is not None and job.request.session_id != session_id:
                return False
            if job.status in TERMINAL_STATES:
                return job.status == TranscriptionStatus.CANCELED
            self._transition(job, TranscriptionStatus.CANCELED)
            task = job.task
        if isinstance(task, asyncio.Task):
            task.cancel()
        return True

    async def cancel_connection(self, connection_id: UUID) -> None:
        await self._cancel_matching(lambda job: job.request.connection_id == connection_id)

    async def cancel_session(self, session_id: UUID) -> None:
        await self._cancel_matching(lambda job: job.request.session_id == session_id)

    async def _cancel_matching(self, predicate: Callable[[TranscriptionJob], bool]) -> None:
        async with self._lock:
            tasks = []
            for job in self._jobs.values():
                if predicate(job) and job.status not in TERMINAL_STATES:
                    self._transition(job, TranscriptionStatus.CANCELED)
                    if isinstance(job.task, asyncio.Task):
                        tasks.append(job.task)
        for task in tasks:
            task.cancel()

    async def counts(self) -> tuple[int, int]:
        async with self._lock:
            queued = sum(job.status == TranscriptionStatus.QUEUED for job in self._jobs.values())
            active = sum(job.status in {TranscriptionStatus.PREPARING, TranscriptionStatus.TRANSCRIBING, TranscriptionStatus.PARTIAL} for job in self._jobs.values())
            return queued, active

    async def cleanup_terminal(self) -> None:
        async with self._lock:
            terminal = [identifier for identifier, job in self._jobs.items() if job.status in TERMINAL_STATES]
            for identifier in terminal:
                job = self._jobs.pop(identifier)
                self._turns.pop((job.request.connection_id, job.request.audio_session_id, job.request.turn_id), None)

    def _transition(self, job: TranscriptionJob, target: TranscriptionStatus) -> None:
        if job.status == target:
            return
        if target not in ALLOWED_TRANSITIONS.get(job.status, set()):
            raise ValueError("invalid_job_state")
        job.status = target

    async def _run(self, job: TranscriptionJob) -> None:
        try:
            async with self._semaphore:
                if job.status == TranscriptionStatus.CANCELED:
                    return
                self._transition(job, TranscriptionStatus.PREPARING)
                await self._publish(job, "transcript.started", {})
                session = await self._provider.start(job.request)
                self._transition(job, TranscriptionStatus.TRANSCRIBING)
                async with asyncio.timeout(self._timeout):
                    async for result in session.results():
                        if job.status in TERMINAL_STATES:
                            return
                        if isinstance(result, PartialTranscript):
                            self._transition(job, TranscriptionStatus.PARTIAL)
                            await self._publish(job, "transcript.partial", {"text": result.text, "sequence": result.sequence, "is_final": False})
                        else:
                            self._transition(job, TranscriptionStatus.COMPLETED)
                            await self._publish(job, "transcript.final", {"text": result.text, "language": result.language.code, "confidence": result.confidence.value if result.confidence else None, "is_final": True})
                            return
                self._transition(job, TranscriptionStatus.FAILED)
        except asyncio.CancelledError:
            await self._publish(job, "transcript.canceled", {})
            return
        except TimeoutError:
            if job.status not in TERMINAL_STATES:
                self._transition(job, TranscriptionStatus.TIMED_OUT)
                await self._publish(job, "transcript.error", {"code": "transcription_timeout"})
        except Exception:
            if job.status not in TERMINAL_STATES:
                self._transition(job, TranscriptionStatus.FAILED)
                await self._publish(job, "transcript.error", {"code": "provider_failure"})
