"""Deterministic local fake wake-word detector for development and tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from tara_api.domain.wakeword import (
    WakeWordConfidence,
    WakeWordDetectionRequest,
    WakeWordDetectionResult,
    WakeWordError,
    WakeWordFailure,
)


@dataclass(frozen=True, slots=True)
class FakeWakeWordBehavior:
    detected: bool = False
    confidence: float | None = None
    delay_seconds: float = 0
    unavailable: bool = False
    malformed_result: bool = False

    def __post_init__(self) -> None:
        if self.delay_seconds < 0:
            raise ValueError("fake wake-word delay must not be negative")


class FakeWakeWordDetector:
    """A deterministic, no-network detector that never accesses a microphone."""

    name = "fake"
    offline_capable = True

    def __init__(self, behaviors: tuple[FakeWakeWordBehavior, ...] = (), *, repeat: bool = False, environment: str = "test") -> None:
        if environment not in {"development", "test"}:
            raise ValueError("fake wake-word detector is development/test only")
        self._behaviors = behaviors or (FakeWakeWordBehavior(),)
        self._repeat = repeat
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    async def detect(self, request: WakeWordDetectionRequest) -> WakeWordDetectionResult:
        behavior = self._behavior()
        self._calls += 1
        if behavior.delay_seconds:
            await asyncio.sleep(behavior.delay_seconds)
        if behavior.unavailable:
            raise WakeWordFailure(WakeWordError.PROVIDER_UNAVAILABLE)
        if behavior.malformed_result:
            return object()  # type: ignore[return-value]
        confidence = WakeWordConfidence(behavior.confidence) if behavior.confidence is not None else None
        return WakeWordDetectionResult(behavior.detected, confidence, self.name, datetime.now(UTC))

    async def readiness(self) -> bool:
        return not self._behaviors[0].unavailable

    def _behavior(self) -> FakeWakeWordBehavior:
        index = self._calls
        if self._repeat:
            return self._behaviors[index % len(self._behaviors)]
        return self._behaviors[min(index, len(self._behaviors) - 1)]
