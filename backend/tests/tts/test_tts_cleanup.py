import asyncio

from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_connection_session_and_shutdown_cleanup_cancel_only_matching_work() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    first_context, second_context = context(), context()
    first_connection, second_connection = __import__("uuid").uuid4(), __import__("uuid").uuid4()
    sessions.active.update({(first_context.owner.id, first_context.session.id), (second_context.owner.id, second_context.session.id)})
    first = response(source, first_context, connection_id=first_connection)
    second = response(source, second_context, connection_id=second_connection)
    tts = service(sessions, source, CountingProvider(delay_seconds=1))
    first_handle = await tts.begin(first_context, command(first), connection_id=first_connection)
    second_handle = await tts.begin(second_context, command(second), connection_id=second_connection)
    await asyncio.sleep(0)
    await tts.cancel_connection(first_connection)
    assert (await tts._registry.wait(first_handle)).state.value == "canceled"  # type: ignore[attr-defined]
    assert (await tts._registry.counts())[0] + (await tts._registry.counts())[1] >= 1  # type: ignore[attr-defined]
    await tts.cancel_session(second_context.owner.id, second_context.session.id)
    assert (await tts._registry.wait(second_handle)).state.value == "canceled"  # type: ignore[attr-defined]
    await tts.shutdown()
