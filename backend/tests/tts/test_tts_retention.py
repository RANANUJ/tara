from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_consumption_and_shutdown_release_transient_audio() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    item = response(source, owner_context)
    tts = service(sessions, source, CountingProvider(audio_bytes=8), maximum_retained_audio_bytes=8)

    result = await tts.submit(owner_context, command(item))
    assert result.result is not None
    assert (await tts._registry.counts())[3] == 0  # type: ignore[attr-defined]
    await tts.shutdown()
    assert (await tts._registry.counts())[3] == 0  # type: ignore[attr-defined]
