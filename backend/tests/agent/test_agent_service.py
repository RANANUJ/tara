import pytest

from tara_api.agent.service import AgentServiceFailure
from tara_api.domain.agent import AgentError, AgentInputSource, AgentState, AgentSubmission, ModelProviderFailure

from .conftest import CountingProvider, owner_context, service


async def test_direct_and_final_transcript_use_one_service_boundary(active_sessions, memory_store) -> None:
    context = owner_context()
    active_sessions.active.add((context.owner.id, context.session.id))
    provider = CountingProvider()
    agent = service(active_sessions, memory_store, provider)

    direct = await agent.submit(context, AgentSubmission("hello", AgentInputSource.DIRECT_TEXT, "one"))
    transcript = await agent.submit_final_transcript(context, "from speech", __import__("uuid").uuid4())

    assert direct.state is AgentState.COMPLETED
    assert transcript.state is AgentState.COMPLETED
    assert provider.calls == 2
    assert await agent.submit_partial_transcript(context, "partial") is None
    await agent.shutdown()


@pytest.mark.parametrize(
    ("text", "expected_error"),
    (("maybe", AgentError.AMBIGUOUS_INTENT), ("Send a message to Sam", AgentError.CONSEQUENTIAL_ACTION_NOT_ENABLED)),
)
async def test_deterministic_routes_do_not_call_the_provider(active_sessions, memory_store, text, expected_error) -> None:
    context = owner_context()
    active_sessions.active.add((context.owner.id, context.session.id))
    provider = CountingProvider()

    agent = service(active_sessions, memory_store, provider)
    response = await agent.submit(context, AgentSubmission(text, AgentInputSource.DIRECT_TEXT, text))

    assert response.state is AgentState.COMPLETED
    assert response.error is expected_error
    assert provider.calls == 0
    await agent.shutdown()


async def test_provider_failure_is_typed_and_isolated(active_sessions, memory_store) -> None:
    context = owner_context()
    active_sessions.active.add((context.owner.id, context.session.id))
    failed = service(active_sessions, memory_store, CountingProvider(failure=ModelProviderFailure(AgentError.PROVIDER_UNAVAILABLE)))

    response = await failed.submit(context, AgentSubmission("hello", AgentInputSource.DIRECT_TEXT, "failure"))

    assert response.state is AgentState.FAILED
    assert response.error is AgentError.PROVIDER_UNAVAILABLE
    await failed.shutdown()


def test_submission_rejects_empty_or_unkeyed_direct_input() -> None:
    with pytest.raises(ValueError):
        AgentSubmission("", AgentInputSource.DIRECT_TEXT, "key")
    with pytest.raises(ValueError):
        AgentSubmission("hello", AgentInputSource.DIRECT_TEXT)


async def test_revoked_session_rejects_new_work(active_sessions, memory_store) -> None:
    context = owner_context()
    with pytest.raises(AgentServiceFailure) as error:
        await service(active_sessions, memory_store, CountingProvider()).submit(context, AgentSubmission("hello", AgentInputSource.DIRECT_TEXT, "key"))
    assert error.value.code is AgentError.SESSION_INVALIDATED
