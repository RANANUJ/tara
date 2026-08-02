import asyncio

import pytest

from tara_api.domain.tts import SpeechSynthesisError
from tara_api.tts.service import TextToSpeechServiceFailure

from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_queue_is_fifo_and_concurrent_provider_calls_are_bounded() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    first, second = response(source, owner_context), response(source, owner_context)
    provider = CountingProvider(delay_seconds=0.01)
    tts = service(sessions, source, provider, maximum_concurrent=1)

    await asyncio.gather(tts.submit(owner_context, command(first)), tts.submit(owner_context, command(second)))

    assert provider.calls == 2
    assert provider.maximum_running == 1
    await tts.shutdown()


async def test_identity_limits_reject_without_partial_registration() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    connection_id = __import__("uuid").uuid4()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    first, second = response(source, owner_context, connection_id=connection_id), response(source, owner_context, connection_id=connection_id)
    tts = service(sessions, source, CountingProvider(delay_seconds=0.05), maximum_per_connection=1)
    pending = asyncio.create_task(tts.submit(owner_context, command(first), connection_id=connection_id))
    await asyncio.sleep(0)
    with pytest.raises(TextToSpeechServiceFailure) as failure:
        await tts.begin(owner_context, command(second), connection_id=connection_id)
    assert failure.value.code is SpeechSynthesisError.CONNECTION_REQUEST_LIMIT
    await pending
    await tts.shutdown()
