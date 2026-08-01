import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.agent.fake import FakeLanguageModelBehavior, FakeLanguageModelProvider
from tara_api.domain.agent import AgentError, ModelMessage, ModelProviderFailure, ModelRequest, ModelRole


def request() -> ModelRequest:
    return ModelRequest(uuid4(), (ModelMessage(ModelRole.USER, "hello"),), 128, 32, datetime.now(UTC))


async def test_fake_provider_is_deterministic_with_usage() -> None:
    provider = FakeLanguageModelProvider(environment="test")
    response = await provider.generate(request())

    assert response.text == "Tara test response."
    assert response.usage is not None
    assert response.usage.output_tokens == 4


async def test_fake_provider_supports_delay_timeout_cancellation_and_unavailability() -> None:
    delayed = FakeLanguageModelProvider(FakeLanguageModelBehavior(delay_seconds=0.01), environment="test")
    assert (await delayed.generate(request())).text

    timed_out = FakeLanguageModelProvider(FakeLanguageModelBehavior(delay_seconds=0.02), timeout_seconds=0.01, environment="test")
    with pytest.raises(ModelProviderFailure, match="timed out") as error:
        await timed_out.generate(request())
    assert error.value.code is AgentError.PROVIDER_TIMEOUT

    canceled = FakeLanguageModelProvider(FakeLanguageModelBehavior(delay_seconds=1), environment="test")
    task = asyncio.create_task(canceled.generate(request()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    unavailable = FakeLanguageModelProvider(FakeLanguageModelBehavior(unavailable=True), environment="test")
    with pytest.raises(ModelProviderFailure) as unavailable_error:
        await unavailable.generate(request())
    assert unavailable_error.value.code is AgentError.PROVIDER_UNAVAILABLE


@pytest.mark.parametrize(
    ("behavior", "code"),
    (
        (FakeLanguageModelBehavior(malformed=True), AgentError.INVALID_PROVIDER_RESPONSE),
        (FakeLanguageModelBehavior(excessive_output=True), AgentError.RESPONSE_TOO_LARGE),
        (FakeLanguageModelBehavior(invalid_unicode=True), AgentError.INVALID_PROVIDER_RESPONSE),
    ),
)
async def test_fake_provider_rejects_bad_output(behavior: FakeLanguageModelBehavior, code: AgentError) -> None:
    with pytest.raises(ModelProviderFailure) as error:
        await FakeLanguageModelProvider(behavior, environment="test").generate(request())
    assert error.value.code is code


def test_fake_provider_rejects_production() -> None:
    with pytest.raises(ValueError):
        FakeLanguageModelProvider(environment="production")
