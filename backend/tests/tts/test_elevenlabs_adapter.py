import httpx
import pytest
from pydantic import SecretStr

from tara_api.domain.tts import SpeechFormat, SpeechSynthesisError, SpeechSynthesisFailure, SpeechVoice
from tara_api.tts.elevenlabs import ElevenLabsTextToSpeechProvider

from .conftest import request


async def test_optional_elevenlabs_adapter_uses_mocked_http_only() -> None:
    seen: list[httpx.Request] = []

    async def handler(item: httpx.Request) -> httpx.Response:
        seen.append(item)
        return httpx.Response(200, content=b"\0\0" * 220)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.elevenlabs.io/v1")
    provider = ElevenLabsTextToSpeechProvider(SecretStr("server-only-key"), SpeechVoice("local-voice"), "eleven-test", output_format=SpeechFormat(), http_client=client)
    result = await provider.synthesize(request())
    assert result.sample_count == 220
    assert seen[0].headers["xi-api-key"] == "server-only-key"
    assert seen[0].url.path.endswith("/text-to-speech/local-voice")


async def test_elevenlabs_errors_are_sanitized() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda item: httpx.Response(500, text="sensitive provider output")), base_url="https://api.elevenlabs.io/v1")
    provider = ElevenLabsTextToSpeechProvider(SecretStr("server-only-key"), SpeechVoice("local-voice"), "eleven-test", output_format=SpeechFormat(), http_client=client)
    with pytest.raises(SpeechSynthesisFailure) as error:
        await provider.synthesize(request())
    assert error.value.code is SpeechSynthesisError.PROVIDER_UNAVAILABLE
    assert "sensitive" not in str(error.value)
