"""Safe, non-loading STT health/status adapter."""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from tara_api.domain.health import HealthState
from tara_api.domain.stt import SpeechToTextProvider
from tara_api.stt.service import InMemoryTranscriptionJobs


@dataclass(frozen=True, slots=True)
class SttHealthSnapshot:
    configured: bool
    required: bool
    provider: str
    state: str
    ready: bool
    model_loaded: bool
    language_mode: str
    partial_mode: str
    queue_depth: int
    active_jobs: int
    max_queue: int
    max_concurrency: int
    diagnostic_code: str | None
    checked_at: datetime
    latency_ms: int


class SttHealthProvider:
    def __init__(self, provider: SpeechToTextProvider | None, jobs: InMemoryTranscriptionJobs | None, *, required: bool, environment: str, language_mode: str, partial_mode: str, max_queue: int, max_concurrency: int, timeout_seconds: float) -> None:  # noqa: E501
        self._provider, self._jobs, self._required, self._environment = provider, jobs, required, environment
        self._language_mode, self._partial_mode, self._max_queue, self._max_concurrency, self._timeout = language_mode, partial_mode, max_queue, max_concurrency, timeout_seconds

    async def snapshot(self) -> SttHealthSnapshot:
        started = time.monotonic()
        checked = datetime.now(UTC)
        if self._provider is None:
            return self._result(False, "disabled", False, False, None, checked, started, 0, 0)
        try:
            ready = await asyncio.wait_for(self._provider.readiness(), self._timeout)
            model_loaded = ready
            state, code = ("ready", None) if ready else ("unavailable", "provider_unavailable")
        except TimeoutError:
            ready, model_loaded, state, code = False, False, "degraded", "health_timeout"
        except Exception:
            ready, model_loaded, state, code = False, False, "unavailable", "provider_unavailable"
        queued, active = await self._jobs.counts() if self._jobs else (0, 0)
        return self._result(True, state, ready, model_loaded, code, checked, started, queued, active)

    async def dependency(self) -> tuple[HealthState, str | None]:
        snapshot = await self.snapshot()
        if snapshot.ready:
            return HealthState.HEALTHY, None
        if not snapshot.required:
            return HealthState.DEGRADED, None
        return HealthState.UNAVAILABLE, "STT is unavailable."

    def _result(self, configured: bool, state: str, ready: bool, loaded: bool, code: str | None, checked: datetime, started: float, queued: int, active: int) -> SttHealthSnapshot:
        provider = self._provider.name if self._provider else "disabled"
        if provider == "fake":
            provider = "fake-development"
        return SttHealthSnapshot(configured, self._required, provider, state, ready, loaded, self._language_mode, self._partial_mode, queued, active, self._max_queue, self._max_concurrency, code, checked, max(0, round((time.monotonic() - started) * 1000)))  # noqa: E501
