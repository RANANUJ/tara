import logging

from tara_api.observability.logging import JsonFormatter
from tara_api.tts.fake import FakeTextToSpeechProvider


def test_tts_sensitive_content_is_redacted_from_structured_logs() -> None:
    formatter = JsonFormatter(("tts-api-secret",))
    record = logging.LogRecord(
        "tara_api",
        logging.INFO,
        __file__,
        1,
        "synthesis_completed",
        (),
        None,
    )
    record.event_data = {
        "request_id": "safe-id",
        "text": "private assistant response",
        "audio": b"audio-bytes",
        "api_key": "tts-api-secret",
        "model_path": "/private/model.onnx",
        "stderr": "private process output",
    }
    rendered = formatter.format(record)

    assert "tts-api-secret" not in rendered
    assert "private assistant response" not in rendered
    assert "audio-bytes" not in rendered
    assert "/private/model.onnx" not in rendered
    assert "private process output" not in rendered
    assert "[REDACTED]" in rendered


async def test_fake_provider_never_logs_text_or_audio(caplog) -> None:  # type: ignore[no-untyped-def]
    provider = FakeTextToSpeechProvider(environment="test")
    assert provider.name == "fake"
    assert "audio" not in caplog.text.lower()
