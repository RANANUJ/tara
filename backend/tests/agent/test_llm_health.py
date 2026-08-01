import asyncio

import httpx
import pytest

from tara_api.agent.fake import FakeLanguageModelProvider
from tara_api.agent.health import LocalLanguageModelHealthProvider
from tara_api.agent.ollama import OllamaLanguageModelProvider
from tara_api.config.settings import Settings
from tara_api.domain.agent import AgentError, ProviderHealthState


async def test_health_reports_disabled_and_fake_development() -> None:
    disabled = LocalLanguageModelHealthProvider(None, required=False, environment="test", timeout_seconds=0.1)
    assert (await disabled.snapshot()).state is ProviderHealthState.DISABLED

    fake = LocalLanguageModelHealthProvider(FakeLanguageModelProvider(environment="development"), required=False, environment="development", timeout_seconds=0.1)
    snapshot = await fake.snapshot()
    assert snapshot.provider == "fake-development"
    assert snapshot.ready is True

    production = LocalLanguageModelHealthProvider(FakeLanguageModelProvider(environment="development"), required=True, environment="production", timeout_seconds=0.1)
    production_snapshot = await production.snapshot()
    assert production_snapshot.ready is False
    assert production_snapshot.diagnostic_code is AgentError.PROVIDER_NOT_CONFIGURED


async def test_health_reports_mocked_ollama_ready_unavailable_and_timeout() -> None:
    ready_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"models": [{"name": "local-model"}]})), base_url="http://ollama.test")
    ready_provider = OllamaLanguageModelProvider("http://ollama.test", "local-model", timeout_seconds=1, context_token_budget=128, output_token_budget=32, temperature=0.2, http_client=ready_client)
    assert (await LocalLanguageModelHealthProvider(ready_provider, required=False, environment="test", timeout_seconds=0.1).snapshot()).state is ProviderHealthState.READY

    unavailable_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("unavailable", request=request))), base_url="http://ollama.test")
    unavailable_provider = OllamaLanguageModelProvider("http://ollama.test", "local-model", timeout_seconds=1, context_token_budget=128, output_token_budget=32, temperature=0.2, http_client=unavailable_client)
    unavailable = await LocalLanguageModelHealthProvider(unavailable_provider, required=False, environment="test", timeout_seconds=0.1).snapshot()
    assert unavailable.diagnostic_code is AgentError.PROVIDER_UNAVAILABLE

    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"models": []})

    timeout_client = httpx.AsyncClient(transport=httpx.MockTransport(slow), base_url="http://ollama.test")
    timeout_provider = OllamaLanguageModelProvider("http://ollama.test", "local-model", timeout_seconds=1, context_token_budget=128, output_token_budget=32, temperature=0.2, http_client=timeout_client)
    timeout = await LocalLanguageModelHealthProvider(timeout_provider, required=False, environment="test", timeout_seconds=0.01).snapshot()
    assert timeout.state is ProviderHealthState.DEGRADED


def test_settings_reject_production_fake_and_unsafe_ollama_combinations() -> None:
    with pytest.raises(ValueError, match="fake language-model"):
        Settings(_env_file=None, environment="production", stt_provider="disabled", llm_provider="fake")
    with pytest.raises(ValueError, match="requires a model"):
        Settings(_env_file=None, llm_provider="ollama")
    with pytest.raises(ValueError, match="invalid Ollama"):
        Settings(_env_file=None, ollama_base_url="http://user:password@ollama.test")
