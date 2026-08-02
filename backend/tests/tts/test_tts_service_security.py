import logging

import pytest

from tara_api.domain.tts import SpeechSynthesisError
from tara_api.observability.logging import JsonFormatter
from tara_api.tts.service import TextToSpeechServiceFailure

from .m10b_conftest import ActiveSessions, CountingProvider, ResponseSource, command, context, response, service


async def test_source_binding_blocks_cross_connection_and_logs_redact_tts_data() -> None:
    sessions, source = ActiveSessions(), ResponseSource()
    owner_context = context()
    sessions.active.add((owner_context.owner.id, owner_context.session.id))
    connection_id = __import__("uuid").uuid4()
    item = response(source, owner_context, connection_id=connection_id, text="private assistant text")
    tts = service(sessions, source, CountingProvider())

    with pytest.raises(TextToSpeechServiceFailure) as failure:
        await tts.begin(owner_context, command(item), connection_id=__import__("uuid").uuid4())
    assert failure.value.code is SpeechSynthesisError.INVALID_AGENT_SOURCE
    record = logging.LogRecord("tara_api", logging.INFO, __file__, 1, "event", (), None)
    record.event_data = {"text": item.text, "audio": b"bytes", "token": "ticket", "provider_stderr": "path"}
    formatted = JsonFormatter().format(record)
    assert item.text not in formatted and "bytes" not in formatted and "ticket" not in formatted
    await tts.shutdown()
