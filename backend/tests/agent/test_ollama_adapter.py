import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from tara_api.agent.ollama import OllamaLanguageModelProvider
from tara_api.domain.agent import AgentError, ModelMessage, ModelProviderFailure, ModelRequest, ModelRole


def request(messages: tuple[ModelMessage, ...] | None = None, *, context: int = 128, output: int = 32) -> ModelRequest:
    return ModelRequest(uuid4(), messages or (ModelMessage(ModelRole.USER, "hello"),), context, output, datetime.now(UTC))


def provider(handler: httpx.AsyncBaseTransport, *, timeout_seconds: float = 1) -> OllamaLanguageModelProvider:
    client = httpx.AsyncClient(transport=handler, base_url="http://ollama.test")
    return OllamaLanguageModelProvider("http://ollama.test", "local-model", timeout_seconds=timeout_seconds, context_token_budget=128, output_token_budget=32, temperature=0.2, http_client=client)


async def test_ollama_maps_roles_request_and_response() -> None:
    captured: dict[str, object] = {}

    def handler(raw: httpx.Request) -> httpx.Response:
        captured.update(json.loads(raw.content))
        return httpx.Response(200, json={"message": {"content": "answer"}, "done_reason": "stop", "prompt_eval_count": 3, "eval_count": 4})

    item = provider(httpx.MockTransport(handler))
    response = await item.generate(request((ModelMessage(ModelRole.SYSTEM, "system"), ModelMessage(ModelRole.USER, "user"), ModelMessage(ModelRole.ASSISTANT, "assistant"))))

    assert captured["model"] == "local-model"
    assert captured["stream"] is False
    assert response.text == "answer"
    assert response.usage is not None and response.usage.input_tokens == 3


async def test_ollama_absent_usage_is_not_fabricated_and_failures_are_sanitized() -> None:
    item = provider(httpx.MockTransport(lambda _request: httpx.Response(200, json={"message": {"content": "answer"}})))
    assert (await item.generate(request())).usage is None

    unavailable = provider(httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("private host", request=request))))
    with pytest.raises(ModelProviderFailure) as error:
        await unavailable.generate(request())
    assert error.value.code is AgentError.PROVIDER_UNAVAILABLE
    assert "private host" not in str(error.value)


async def test_ollama_rejects_invalid_output_timeout_and_cancellation() -> None:
    malformed = provider(httpx.MockTransport(lambda _request: httpx.Response(200, json={"message": {"content": ""}})))
    with pytest.raises(ModelProviderFailure) as malformed_error:
        await malformed.generate(request())
    assert malformed_error.value.code is AgentError.INVALID_PROVIDER_RESPONSE

    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"message": {"content": "late"}})

    timed_out = provider(httpx.MockTransport(slow), timeout_seconds=0.01)
    with pytest.raises(ModelProviderFailure) as timeout_error:
        await timed_out.generate(request())
    assert timeout_error.value.code is AgentError.PROVIDER_TIMEOUT

    canceled = provider(httpx.MockTransport(slow))
    task = asyncio.create_task(canceled.generate(request()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_ollama_enforces_budgets_without_pull_requests() -> None:
    calls: list[str] = []

    def handler(raw: httpx.Request) -> httpx.Response:
        calls.append(raw.url.path)
        return httpx.Response(200, json={"message": {"content": "answer"}})

    item = provider(httpx.MockTransport(handler))
    with pytest.raises(ModelProviderFailure) as error:
        await item.generate(request(context=129))
    assert error.value.code is AgentError.CONTEXT_LIMIT_EXCEEDED
    assert calls == []
    assert "pull" not in " ".join(calls)


def test_ollama_configuration_rejects_credentials_model_absence_and_streaming() -> None:
    with pytest.raises(ValueError):
        OllamaLanguageModelProvider("http://user:password@ollama.test", "model", timeout_seconds=1, context_token_budget=1, output_token_budget=1, temperature=0)
    with pytest.raises(ValueError):
        OllamaLanguageModelProvider("http://ollama.test", "", timeout_seconds=1, context_token_budget=1, output_token_budget=1, temperature=0)
    with pytest.raises(ValueError):
        OllamaLanguageModelProvider("http://ollama.test", "model", timeout_seconds=1, context_token_budget=1, output_token_budget=1, temperature=0, streaming=True)
