"""Centralized input and provider-result validation for M10A TTS."""

from __future__ import annotations

from datetime import UTC, datetime

from tara_api.domain.tts import (
    MAX_SYNTHESIS_AUDIO_BYTES,
    MAX_SYNTHESIS_TEXT_CHARS,
    SpeechAudioChunk,
    SpeechSynthesisError,
    SpeechSynthesisFailure,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechTimingMetadata,
    SpeechUsageMetadata,
)


def normalize_synthesis_text(text: str) -> str:
    """Return one safe, deterministic text form without SSML support."""

    if not isinstance(text, str):
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_TEXT)
    if "\x00" in text:
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_TEXT)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_TEXT) from error
    normalized = " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())
    if not normalized:
        raise SpeechSynthesisFailure(SpeechSynthesisError.EMPTY_TEXT)
    if len(normalized) > MAX_SYNTHESIS_TEXT_CHARS:
        raise SpeechSynthesisFailure(SpeechSynthesisError.TEXT_TOO_LONG)
    return normalized


def validated_request(request: SpeechSynthesisRequest) -> SpeechSynthesisRequest:
    normalized = normalize_synthesis_text(request.text)
    if normalized == request.text:
        return request
    return SpeechSynthesisRequest(
        request.synthesis_id,
        request.owner_id,
        request.session_id,
        normalized,
        request.voice,
        request.language,
        request.output_format,
        request.created_at,
    )


def validated_result(
    request: SpeechSynthesisRequest,
    audio: bytes,
    *,
    synthesis_duration_ms: int,
    completed_at: datetime | None = None,
    chunks: tuple[SpeechAudioChunk, ...] = (),
) -> SpeechSynthesisResult:
    if not audio:
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_AUDIO_RESPONSE)
    if len(audio) > MAX_SYNTHESIS_AUDIO_BYTES:
        raise SpeechSynthesisFailure(SpeechSynthesisError.AUDIO_TOO_LARGE)
    if len(audio) % request.output_format.bytes_per_frame:
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_AUDIO_METADATA)
    sample_count = len(audio) // request.output_format.bytes_per_frame
    duration_ms = round(sample_count * 1000 / request.output_format.sample_rate)
    try:
        return SpeechSynthesisResult(
            request.synthesis_id,
            audio,
            request.output_format,
            sample_count,
            SpeechTimingMetadata(synthesis_duration_ms, duration_ms),
            SpeechUsageMetadata(len(request.text), len(audio)),
            completed_at or datetime.now(UTC),
            chunks,
        )
    except ValueError as error:
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_AUDIO_METADATA) from error
