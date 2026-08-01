"""Safe local language-model health foundation without application integration."""

import asyncio
import time
from datetime import UTC, datetime

from tara_api.domain.agent import AgentError, LanguageModelHealthSnapshot, LanguageModelProvider, ModelReadiness, ProviderHealthState


class LocalLanguageModelHealthProvider:
    def __init__(self, provider: LanguageModelProvider | None, *, required: bool, environment: str, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._provider = provider
        self._required = required
        self._environment = environment
        self._timeout_seconds = timeout_seconds

    async def snapshot(self) -> LanguageModelHealthSnapshot:
        started = time.monotonic()
        checked_at = datetime.now(UTC)
        if self._provider is None:
            return self._snapshot(False, "disabled", None, ProviderHealthState.DISABLED, False, False, checked_at, started, None)
        if self._provider.name == "fake" and self._environment == "production":
            return self._snapshot(True, "fake-production", self._provider.model_identifier, ProviderHealthState.UNAVAILABLE, False, False, checked_at, started, AgentError.PROVIDER_NOT_CONFIGURED)
        try:
            readiness = await asyncio.wait_for(self._provider.readiness(), self._timeout_seconds)
        except TimeoutError:
            readiness = ModelReadiness(False, ProviderHealthState.DEGRADED, AgentError.PROVIDER_TIMEOUT)
        except Exception:
            readiness = ModelReadiness(False, ProviderHealthState.UNAVAILABLE, AgentError.PROVIDER_UNAVAILABLE)
        provider = self._provider.name
        if provider == "fake":
            provider = f"fake-{self._environment}"
        return self._snapshot(True, provider, self._provider.model_identifier, readiness.state, readiness.ready, self._provider.streaming_supported, checked_at, started, readiness.diagnostic_code)

    def _snapshot(
        self,
        configured: bool,
        provider: str,
        model: str | None,
        state: ProviderHealthState,
        ready: bool,
        streaming_supported: bool,
        checked_at: datetime,
        started: float,
        diagnostic_code: AgentError | None,
    ) -> LanguageModelHealthSnapshot:
        return LanguageModelHealthSnapshot(configured, self._required, provider, model, state, ready, streaming_supported, checked_at, max(0, round((time.monotonic() - started) * 1000)), diagnostic_code)
