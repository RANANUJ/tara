"""Deterministic post-synthesis PCM chunking for a later transport milestone."""

from __future__ import annotations

from tara_api.domain.tts import SpeechAudioChunk, SpeechSynthesisError, SpeechSynthesisFailure, SpeechSynthesisResult


def chunk_synthesized_audio(result: SpeechSynthesisResult, maximum_chunk_bytes: int) -> tuple[SpeechAudioChunk, ...]:
    """Split final raw PCM into ordered frame-aligned transport chunks, never WAV fragments."""

    frame_size = result.output_format.bytes_per_frame
    if maximum_chunk_bytes < frame_size or maximum_chunk_bytes > len(result.audio) or maximum_chunk_bytes % frame_size:
        raise SpeechSynthesisFailure(SpeechSynthesisError.INVALID_AUDIO_METADATA)
    chunks: list[SpeechAudioChunk] = []
    for sequence, offset in enumerate(range(0, len(result.audio), maximum_chunk_bytes)):
        audio = result.audio[offset : offset + maximum_chunk_bytes]
        start_samples = offset // frame_size
        end_samples = (offset + len(audio)) // frame_size
        chunks.append(
            SpeechAudioChunk(
                sequence,
                audio,
                is_final=offset + len(audio) == len(result.audio),
                byte_offset=offset,
                byte_length=len(audio),
                start_duration_ms=round(start_samples * 1000 / result.output_format.sample_rate),
                end_duration_ms=round(end_samples * 1000 / result.output_format.sample_rate),
            )
        )
    return tuple(chunks)
