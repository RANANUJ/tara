import asyncio

from tara_api.domain.agent import AgentInputSource, AgentState, AgentSubmission

from .conftest import CountingProvider, owner_context, service


async def test_concurrent_duplicate_direct_request_calls_provider_once(active_sessions, memory_store) -> None:
    context = owner_context()
    active_sessions.active.add((context.owner.id, context.session.id))
    provider = CountingProvider(delay_seconds=0.02)
    agent = service(active_sessions, memory_store, provider)
    submission = AgentSubmission("hello", AgentInputSource.DIRECT_TEXT, "same-key")

    first, second = await asyncio.gather(agent.submit(context, submission), agent.submit(context, submission))

    assert first.state is second.state is AgentState.COMPLETED
    assert first.request_id == second.request_id
    assert provider.calls == 1
    await agent.shutdown()


async def test_same_key_is_isolated_by_session(active_sessions, memory_store) -> None:
    first = owner_context()
    second = owner_context(first.owner.id)
    active_sessions.active.update({(first.owner.id, first.session.id), (second.owner.id, second.session.id)})
    provider = CountingProvider()
    agent = service(active_sessions, memory_store, provider)

    await agent.submit(first, AgentSubmission("hello", AgentInputSource.DIRECT_TEXT, "shared"))
    await agent.submit(second, AgentSubmission("hello", AgentInputSource.DIRECT_TEXT, "shared"))

    assert provider.calls == 2
    await agent.shutdown()
