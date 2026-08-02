import asyncio

import pytest

from tara_api.tts.service import TextToSpeechServiceFailure

from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_concurrent_duplicate_submission_creates_one_job() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context)
    provider = CountingProvider(delay_seconds=0.01)
    tts = service(sessions, source, provider)

    first, second = await asyncio.gather(tts.begin(owner_context, command(item)), tts.begin(owner_context, command(item)))
    assert first.identity.synthesis_request_id == second.identity.synthesis_request_id
    await asyncio.gather(tts.complete(first), tts.complete(second))
    assert provider.calls == 1
    await tts.shutdown()


async def test_same_source_identity_is_scoped_to_its_owner_session() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    first_context, second_context = context(), context()
    sessions.active.update({(first_context.owner.id, first_context.session.id), (second_context.owner.id, second_context.session.id)})
    item = response(source, first_context)
    tts = service(sessions, source, CountingProvider())

    assert (await tts.begin(first_context, command(item))).created
    with pytest.raises(TextToSpeechServiceFailure):
        await tts.begin(second_context, command(item))
    await tts.shutdown()
