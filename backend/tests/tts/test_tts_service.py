import pytest

from tara_api.domain.tts import SpeechSynthesisError, SpeechSynthesisState
from tara_api.tts.service import TextToSpeechServiceFailure

from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_completed_agent_response_synthesizes_once() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context)
    provider = CountingProvider()
    tts = service(sessions, source, provider)

    result = await tts.submit(owner_context, command(item))

    assert result.record.state is SpeechSynthesisState.COMPLETED
    assert result.result is not None
    assert provider.calls == 1
    await tts.shutdown()


@pytest.mark.parametrize("text,error", [("   ", SpeechSynthesisError.EMPTY_TEXT), ("x" * 4001, SpeechSynthesisError.TEXT_TOO_LONG)])
async def test_invalid_approved_text_is_rejected(text, error) -> None:  # type: ignore[no-untyped-def]
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context, text=text)
    tts = service(sessions, source, CountingProvider())

    with pytest.raises(TextToSpeechServiceFailure) as failure:
        await tts.submit(owner_context, command(item))
    assert failure.value.code is error
    await tts.shutdown()


async def test_unavailable_provider_and_failed_source_are_safe() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context)
    unavailable = service(sessions, source, None)
    with pytest.raises(TextToSpeechServiceFailure) as failure:
        await unavailable.submit(owner_context, command(item))
    assert failure.value.code is SpeechSynthesisError.PROVIDER_NOT_CONFIGURED

    source.responses.pop(item.agent_request_id)
    blocked = service(sessions, source, CountingProvider())
    with pytest.raises(TextToSpeechServiceFailure) as failure:
        await blocked.submit(owner_context, command(item))
    assert failure.value.code is SpeechSynthesisError.INVALID_AGENT_SOURCE
    await unavailable.shutdown()
    await blocked.shutdown()
