"""Optional final-only ElevenLabs adapter; cloud use is explicit and never default."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from tara_api.domain.tts import (
    SpeechFormat,
    SpeechLanguage,
    SpeechProviderReadiness,
    SpeechProviderState,
    SpeechSynthesisError,
    SpeechSynthesisFailure,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechVoice,
)
from tara_api.tts.validation import validated_request, validated_result


class ElevenLabsTextToSpeechProvider:
    """Bounded server-side adapter for explicitly configured cloud TTS."""

    name = "elevenlabs"
    streaming_supported = False

    def __init__(
        self,
        api_key: SecretStr,
        voice: SpeechVoice,
        model_identifier: str,
        *,
        output_format: SpeechFormat,
        timeout_seconds: float = 30,
        base_url: str = "https://api.elevenlabs.io/v1",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if not api_key.get_secret_value() or not model_identifier or timeout_seconds <= 0 or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid ElevenLabs configuration")
        self._api_key = api_key
        self.voice = voice
        self._model_identifier = model_identifier
        self._output_format = output_format
        self._timeout_seconds = timeout_seconds
        self._client = http_client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=httpx.Timeout(timeout_seconds))
        self.supported_formats = (output_format,)
        self.supported_languages = (SpeechLanguage.ENGLISH, SpeechLanguage.HINDI, SpeechLanguage.MIXED)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        request = validated_request(request)
        self._validate_request(request)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.post(
                    f"/text-to-speech/{self.voice.identifier}",
                    headers={"xi-api-key": self._api_key.get_secret_value(), "accept": "application/octet-stream"},
                    json={"text": request.text, "model_id": self._model_identifier, "output_format": self._output_format_name()},
                )
                response.raise_for_status()
                audio = response.content
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx.TimeoutException) as error:
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_TIMEOUT) from error
        except httpx.HTTPError as error:
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_UNAVAILABLE) from error
        return validated_result(request, audio, synthesis_duration_ms=max(0, round((time.monotonic() - started) * 1000)))

    async def readiness(self) -> SpeechProviderReadiness:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.get(f"/voices/{self.voice.identifier}", headers={"xi-api-key": self._api_key.get_secret_value()})
                response.raise_for_status()
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            return SpeechProviderReadiness(False, SpeechProviderState.DEGRADED, SpeechSynthesisError.PROVIDER_TIMEOUT)
        except httpx.HTTPError:
            return SpeechProviderReadiness(False, SpeechProviderState.UNAVAILABLE, SpeechSynthesisError.PROVIDER_UNAVAILABLE)
        return SpeechProviderReadiness(True, SpeechProviderState.READY)

    def _validate_request(self, request: SpeechSynthesisRequest) -> None:
        if request.voice != self.voice:
            raise SpeechSynthesisFailure(SpeechSynthesisError.VOICE_NOT_AVAILABLE)
        if request.language not in self.supported_languages:
            raise SpeechSynthesisFailure(SpeechSynthesisError.LANGUAGE_NOT_SUPPORTED)
        if request.output_format not in self.supported_formats:
            raise SpeechSynthesisFailure(SpeechSynthesisError.FORMAT_NOT_SUPPORTED)

    def _output_format_name(self) -> str:
        return f"pcm_{self._output_format.sample_rate}"
