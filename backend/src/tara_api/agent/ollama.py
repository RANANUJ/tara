"""Final-only Ollama HTTP adapter with bounded, sanitized provider behavior."""

import asyncio
import time
from typing import Final
from urllib.parse import urlsplit

import httpx

from tara_api.agent.validation import DefaultModelRequestValidator, DefaultModelResponseValidator
from tara_api.domain.agent import AgentError, ModelFinishReason, ModelProviderFailure, ModelReadiness, ModelRequest, ModelResponse, ModelUsage, ProviderHealthState

_SUPPORTED_ROLES: Final = {"system", "user", "assistant"}


class OllamaLanguageModelProvider:
    """Map framework-neutral model requests to Ollama's local HTTP API."""

    name = "ollama"
    streaming_supported = False

    def __init__(self, base_url: str, model_identifier: str, *, timeout_seconds: float, context_token_budget: int, output_token_budget: int, temperature: float, streaming: bool = False, http_client: httpx.AsyncClient | None = None) -> None:  # noqa: E501
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid Ollama base URL")
        if not model_identifier or timeout_seconds <= 0 or context_token_budget < 1 or output_token_budget < 1 or not 0 <= temperature <= 1 or streaming:
            raise ValueError("invalid Ollama configuration")
        self.model_identifier = model_identifier
        self._timeout_seconds = timeout_seconds
        self._context_token_budget = context_token_budget
        self._output_token_budget = output_token_budget
        self._temperature = temperature
        self._client = http_client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=httpx.Timeout(timeout_seconds))
        self._request_validator = DefaultModelRequestValidator()
        self._response_validator = DefaultModelResponseValidator()

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._request_validator.validate(request)
        if request.context_token_budget > self._context_token_budget or request.output_token_budget > self._output_token_budget:
            raise ModelProviderFailure(AgentError.CONTEXT_LIMIT_EXCEEDED, "The model context is too large.")
        payload = {
            "model": self.model_identifier,
            "messages": self._messages(request),
            "stream": False,
            "options": {"num_ctx": self._context_token_budget, "num_predict": self._output_token_budget, "temperature": self._temperature},
        }
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.post("/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            raise ModelProviderFailure(AgentError.PROVIDER_TIMEOUT, "The language model timed out.") from error
        except httpx.TimeoutException as error:
            raise ModelProviderFailure(AgentError.PROVIDER_TIMEOUT, "The language model timed out.") from error
        except httpx.HTTPError as error:
            raise ModelProviderFailure(AgentError.PROVIDER_UNAVAILABLE, "The language model is unavailable.") from error
        except ValueError as error:
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.") from error
        return self._response_validator.validate(self._response(body, max(0, round((time.monotonic() - started) * 1000))))

    async def readiness(self) -> ModelReadiness:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.get("/api/tags")
                response.raise_for_status()
                body = response.json()
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            return ModelReadiness(False, ProviderHealthState.DEGRADED, AgentError.PROVIDER_TIMEOUT)
        except (ValueError, httpx.HTTPError):
            return ModelReadiness(False, ProviderHealthState.UNAVAILABLE, AgentError.PROVIDER_UNAVAILABLE)
        models = body.get("models") if isinstance(body, dict) else None
        if not isinstance(models, list):
            return ModelReadiness(False, ProviderHealthState.UNAVAILABLE, AgentError.INVALID_PROVIDER_RESPONSE)
        names = {item.get("name") or item.get("model") for item in models if isinstance(item, dict)}
        if self.model_identifier not in names:
            return ModelReadiness(False, ProviderHealthState.UNAVAILABLE, AgentError.MODEL_NOT_AVAILABLE)
        return ModelReadiness(True, ProviderHealthState.READY)

    def _messages(self, request: ModelRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for message in request.messages:
            if not isinstance(message.role, str) or message.role not in _SUPPORTED_ROLES:
                raise ModelProviderFailure(AgentError.REQUEST_TOO_LARGE, "The model request is invalid.")
            messages.append({"role": message.role, "content": message.text})
        return messages

    def _response(self, body: object, duration_ms: int) -> ModelResponse:
        if not isinstance(body, dict) or not isinstance(body.get("message"), dict):
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.")
        message = body["message"]
        text = message.get("content")
        if not isinstance(text, str):
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.")
        finish_reason = ModelFinishReason.LENGTH if body.get("done_reason") == "length" else ModelFinishReason.STOP if body.get("done_reason") == "stop" else ModelFinishReason.UNKNOWN
        usage = self._usage(body)
        try:
            return ModelResponse(text, self.model_identifier, finish_reason, duration_ms, usage)
        except ValueError as error:
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.") from error

    @staticmethod
    def _usage(body: dict[str, object]) -> ModelUsage | None:
        input_tokens = body.get("prompt_eval_count")
        output_tokens = body.get("eval_count")
        if input_tokens is None and output_tokens is None:
            return None
        if (input_tokens is not None and (type(input_tokens) is not int or input_tokens < 0)) or (output_tokens is not None and (type(output_tokens) is not int or output_tokens < 0)):
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.")
        return ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens)
