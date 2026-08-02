import asyncio

from tara_api.domain.tts import SpeechSynthesisError
from tara_api.tts.service import TextToSpeechServiceFailure

from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_active_cancellation_releases_audio_and_suppresses_late_result() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    connection_id = __import__("uuid").uuid4()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context, connection_id=connection_id)
    tts = service(sessions, source, CountingProvider(delay_seconds=1), timeout_seconds=2)
    handle = await tts.begin(owner_context, command(item), connection_id=connection_id)
    await asyncio.sleep(0)

    assert await tts.cancel(owner_context, handle.identity.synthesis_request_id, connection_id=connection_id)
    with __import__("pytest").raises(TextToSpeechServiceFailure) as failure:
        await tts.complete(handle)
    assert failure.value.code is SpeechSynthesisError.REQUEST_CANCELED
    assert not await tts.cancel(owner_context, handle.identity.synthesis_request_id, connection_id=__import__("uuid").uuid4())
    await tts.shutdown()


async def test_timeout_is_terminal() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context)
    tts = service(sessions, source, CountingProvider(delay_seconds=0.05), timeout_seconds=0.001)

    with __import__("pytest").raises(TextToSpeechServiceFailure) as failure:
        await tts.submit(owner_context, command(item))
    assert failure.value.code is SpeechSynthesisError.REQUEST_TIMED_OUT
    await tts.shutdown()
