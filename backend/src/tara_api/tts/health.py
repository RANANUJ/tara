"""Safe, standalone M10A TTS provider-health snapshot."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from tara_api.domain.tts import (
    SpeechProviderHealth,
    SpeechProviderState,
    SpeechSynthesisError,
    TextToSpeechProvider,
)


class LocalTextToSpeechHealthProvider:
    def __init__(self, provider: TextToSpeechProvider | None, *, required: bool, environment: str, language_mode: str, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("TTS health timeout must be positive")
        self._provider = provider
        self._required = required
        self._environment = environment
        self._language_mode = language_mode
        self._timeout_seconds = timeout_seconds

    async def snapshot(self) -> SpeechProviderHealth:
        started = time.monotonic()
        checked_at = datetime.now(UTC)
        if self._provider is None:
            return self._snapshot(False, "disabled", SpeechProviderState.DISABLED, False, checked_at, started, None)
        if self._provider.name == "fake" and self._environment == "production":
            return self._snapshot(True, "fake-production", SpeechProviderState.UNAVAILABLE, False, checked_at, started, SpeechSynthesisError.PROVIDER_NOT_CONFIGURED)
        try:
            readiness = await asyncio.wait_for(self._provider.readiness(), self._timeout_seconds)
        except TimeoutError:
            return self._snapshot(True, self._provider.name, SpeechProviderState.DEGRADED, False, checked_at, started, SpeechSynthesisError.PROVIDER_TIMEOUT)
        except Exception:
            return self._snapshot(True, self._provider.name, SpeechProviderState.UNAVAILABLE, False, checked_at, started, SpeechSynthesisError.PROVIDER_UNAVAILABLE)
        provider = f"fake-{self._environment}" if self._provider.name == "fake" else self._provider.name
        return self._snapshot(True, provider, readiness.state, readiness.ready, checked_at, started, readiness.diagnostic_code)

    def _snapshot(
        self,
        configured: bool,
        provider: str,
        state: SpeechProviderState,
        ready: bool,
        checked_at: datetime,
        started: float,
        diagnostic_code: SpeechSynthesisError | None,
    ) -> SpeechProviderHealth:
        return SpeechProviderHealth(
            configured,
            self._required,
            provider,
            state,
            ready,
            self._provider.voice.identifier if self._provider else None,
            self._language_mode,
            self._provider.supported_formats[0] if self._provider else None,
            self._provider.streaming_supported if self._provider else False,
            checked_at,
            max(0, round((time.monotonic() - started) * 1000)),
            diagnostic_code,
        )
