"""Deterministic test/development TTS provider with no external dependencies."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from tara_api.domain.tts import (
    MAX_SYNTHESIS_AUDIO_BYTES,
    SpeechEncoding,
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

_DEFAULT_VOICE = SpeechVoice("local-voice")


@dataclass(frozen=True, slots=True)
class FakeTextToSpeechBehavior:
    delay_seconds: float = 0
    unavailable: bool = False
    malformed_audio: bool = False
    excessive_audio: bool = False
    invalid_metadata: bool = False
    unsupported_language: bool = False
    unsupported_format: bool = False


class FakeTextToSpeechProvider:
    """Final-only deterministic synthetic PCM for tests and development."""

    name = "fake"
    streaming_supported = False

    def __init__(
        self,
        behavior: FakeTextToSpeechBehavior | None = None,
        *,
        voice: SpeechVoice = _DEFAULT_VOICE,
        timeout_seconds: float = 30,
        environment: str = "test",
    ) -> None:
        if environment not in {"development", "test"} or timeout_seconds <= 0:
            raise ValueError("invalid fake TTS configuration")
        self._behavior = behavior or FakeTextToSpeechBehavior()
        self.voice = voice
        self._timeout_seconds = timeout_seconds
        self._environment = environment
        self.supported_formats = (SpeechFormat(),)
        self.supported_languages = (SpeechLanguage.ENGLISH, SpeechLanguage.HINDI, SpeechLanguage.MIXED)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        request = validated_request(request)
        self._validate_request(request)
        if self._behavior.unavailable:
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_UNAVAILABLE)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                if self._behavior.delay_seconds:
                    await asyncio.sleep(self._behavior.delay_seconds)
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_TIMEOUT) from error
        bytes_per_frame = request.output_format.bytes_per_frame
        sample_count = max(1, len(request.text) * request.output_format.sample_rate // 50)
        audio = b"\0" * (sample_count * bytes_per_frame)
        if self._behavior.excessive_audio:
            audio = b"\0" * (MAX_SYNTHESIS_AUDIO_BYTES + bytes_per_frame)
        if self._behavior.malformed_audio:
            audio = b"\0"
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        if self._behavior.invalid_metadata:
            duration_ms = -1
        return validated_result(request, audio, synthesis_duration_ms=duration_ms, completed_at=datetime.now(UTC))

    async def readiness(self) -> SpeechProviderReadiness:
        if self._behavior.unavailable:
            return SpeechProviderReadiness(False, SpeechProviderState.UNAVAILABLE, SpeechSynthesisError.PROVIDER_UNAVAILABLE)
        return SpeechProviderReadiness(True, SpeechProviderState.READY)

    def _validate_request(self, request: SpeechSynthesisRequest) -> None:
        if request.voice != self.voice:
            raise SpeechSynthesisFailure(SpeechSynthesisError.VOICE_NOT_AVAILABLE)
        if self._behavior.unsupported_language or request.language not in self.supported_languages:
            raise SpeechSynthesisFailure(SpeechSynthesisError.LANGUAGE_NOT_SUPPORTED)
        if self._behavior.unsupported_format or request.output_format not in self.supported_formats or request.output_format.encoding is not SpeechEncoding.PCM_S16LE:
            raise SpeechSynthesisFailure(SpeechSynthesisError.FORMAT_NOT_SUPPORTED)
