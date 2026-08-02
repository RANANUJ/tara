"""Safe, non-activating foreground wake-word health snapshot."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from tara_api.domain.health import HealthState
from tara_api.domain.wakeword import (
    WakeWordConfiguration,
    WakeWordDetector,
    WakeWordError,
    WakeWordProviderHealth,
    WakeWordState,
)


class LocalWakeWordHealthProvider:
    def __init__(self, configuration: WakeWordConfiguration, detector: WakeWordDetector | None, *, required: bool = False, environment: str, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("wake-word health timeout must be positive")
        self._configuration = configuration
        self._detector = detector
        self._required = required
        self._environment = environment
        self._timeout_seconds = timeout_seconds

    async def snapshot(self) -> WakeWordProviderHealth:
        started = time.monotonic()
        checked_at = datetime.now(UTC)
        if self._detector is None or self._configuration.provider == "disabled":
            return self._result(False, "disabled", WakeWordState.DISABLED, False, None, checked_at, started)
        if self._detector.name == "fake" and self._environment == "production":
            return self._result(True, "fake-development", WakeWordState.UNAVAILABLE, False, WakeWordError.PROVIDER_NOT_CONFIGURED, checked_at, started)
        try:
            ready = await asyncio.wait_for(self._detector.readiness(), self._timeout_seconds)
        except TimeoutError:
            return self._result(True, self._provider_name(), WakeWordState.UNAVAILABLE, False, WakeWordError.DETECTOR_TIMEOUT, checked_at, started)
        except Exception:
            return self._result(True, self._provider_name(), WakeWordState.UNAVAILABLE, False, WakeWordError.PROVIDER_UNAVAILABLE, checked_at, started)
        return self._result(True, self._provider_name(), WakeWordState.IDLE if ready else WakeWordState.UNAVAILABLE, ready, None if ready else WakeWordError.PROVIDER_UNAVAILABLE, checked_at, started)

    async def dependency(self) -> tuple[HealthState, str | None]:
        snapshot = await self.snapshot()
        if snapshot.ready or snapshot.state is WakeWordState.DISABLED:
            return HealthState.HEALTHY, None
        if self._required:
            return HealthState.UNAVAILABLE, "Wake word is unavailable."
        return HealthState.DEGRADED, None

    def _provider_name(self) -> str:
        return "fake-development" if self._detector is not None and self._detector.name == "fake" else self._configuration.provider

    def _result(self, configured: bool, provider: str, state: WakeWordState, ready: bool, code: WakeWordError | None, checked_at: datetime, started: float) -> WakeWordProviderHealth:
        return WakeWordProviderHealth(
            configured=configured,
            enabled=self._configuration.enabled,
            provider=provider,
            state=state,
            ready=ready,
            phrase_configured=bool(self._configuration.phrase),
            foreground_only=True,
            offline_capable=bool(self._detector and self._detector.offline_capable),
            streaming_audio_supported=configured,
            continuous_while_page_open=configured,
            native_background_supported=False,
            screen_off_supported=False,
            locked_device_supported=False,
            checked_at=checked_at,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            diagnostic_code=code,
        )
