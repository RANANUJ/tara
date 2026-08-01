"""Deterministic local language-model provider for tests and development."""

import asyncio
import time
from dataclasses import dataclass

from tara_api.agent.validation import DefaultModelRequestValidator, DefaultModelResponseValidator
from tara_api.domain.agent import AgentError, ModelFinishReason, ModelProviderFailure, ModelReadiness, ModelRequest, ModelResponse, ModelUsage, ProviderHealthState


@dataclass(frozen=True, slots=True)
class FakeLanguageModelBehavior:
    response_text: str = "Tara test response."
    delay_seconds: float = 0
    unavailable: bool = False
    malformed: bool = False
    excessive_output: bool = False
    invalid_unicode: bool = False
    usage: ModelUsage | None = ModelUsage(input_tokens=3, output_tokens=4)


class FakeLanguageModelProvider:
    """A deterministic final-only provider with no network behavior."""

    name = "fake"
    streaming_supported = False

    def __init__(self, behavior: FakeLanguageModelBehavior | None = None, *, model_identifier: str = "fake-local", timeout_seconds: float = 30, environment: str = "test") -> None:
        if environment not in {"development", "test"} or timeout_seconds <= 0 or not model_identifier:
            raise ValueError("invalid fake language-model configuration")
        self._behavior = behavior or FakeLanguageModelBehavior()
        self.model_identifier = model_identifier
        self._timeout_seconds = timeout_seconds
        self._request_validator = DefaultModelRequestValidator()
        self._response_validator = DefaultModelResponseValidator()

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._request_validator.validate(request)
        if self._behavior.unavailable:
            raise ModelProviderFailure(AgentError.PROVIDER_UNAVAILABLE, "The language model is unavailable.")
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                if self._behavior.delay_seconds:
                    await asyncio.sleep(self._behavior.delay_seconds)
        except TimeoutError as error:
            raise ModelProviderFailure(AgentError.PROVIDER_TIMEOUT, "The language model timed out.") from error
        if self._behavior.malformed:
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.")
        if self._behavior.excessive_output:
            raise ModelProviderFailure(AgentError.RESPONSE_TOO_LARGE, "The model response is too large.")
        if self._behavior.invalid_unicode:
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.")
        response = ModelResponse(self._behavior.response_text, self.model_identifier, ModelFinishReason.STOP, max(0, round((time.monotonic() - started) * 1000)), self._behavior.usage)
        return self._response_validator.validate(response)

    async def readiness(self) -> ModelReadiness:
        if self._behavior.unavailable:
            return ModelReadiness(False, ProviderHealthState.UNAVAILABLE, AgentError.PROVIDER_UNAVAILABLE)
        return ModelReadiness(True, ProviderHealthState.READY)
