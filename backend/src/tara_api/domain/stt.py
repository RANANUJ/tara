"""Framework-independent M8 speech-to-text contracts."""
# ruff: noqa: E701, E702, E501, I001, UP035
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

class TranscriptionStatus(StrEnum):
    QUEUED="queued"; PREPARING="preparing"; TRANSCRIBING="transcribing"; PARTIAL="partial"; COMPLETED="completed"; CANCELED="canceled"; TIMED_OUT="timed_out"; FAILED="failed"
class TranscriptionError(StrEnum):
    PROVIDER_UNAVAILABLE="provider_unavailable"; AUDIO_TOO_SHORT="audio_too_short"; QUEUE_FULL="queue_full"; TRANSCRIPTION_TIMEOUT="transcription_timeout"; PROVIDER_FAILURE="provider_failure"
@dataclass(frozen=True, slots=True)
class TranscriptLanguage:
    code: str; confidence: float|None=None
    def __post_init__(self)->None:
        if self.code not in {"en","hi","mixed","und"} or self.confidence is not None and not 0<=self.confidence<=1: raise ValueError("invalid language")
@dataclass(frozen=True, slots=True)
class TranscriptionConfidence:
    value: float
    def __post_init__(self)->None:
        if not 0<=self.value<=1: raise ValueError("invalid confidence")
@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_ms:int; end_ms:int; text:str
    def __post_init__(self)->None:
        if self.start_ms<0 or self.end_ms<self.start_ms or not self.text: raise ValueError("invalid segment")
@dataclass(frozen=True, slots=True)
class PartialTranscript: text:str; sequence:int
@dataclass(frozen=True, slots=True)
class FinalTranscript:
    text:str; language:TranscriptLanguage; confidence:TranscriptionConfidence|None=None; segments:tuple[TranscriptSegment,...]=()
    def __post_init__(self)->None:
        if not self.text or len(self.text)>4000: raise ValueError("invalid final")
@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    transcription_id:UUID; owner_id:UUID; session_id:UUID; connection_id:UUID; audio_session_id:UUID; turn_id:UUID; pcm16:bytes; created_at:datetime; language_hint:str|None=None
@dataclass(frozen=True, slots=True)
class TranscriptionResult: final:FinalTranscript
@dataclass(slots=True)
class TranscriptionJob:
    request:TranscriptionRequest; status:TranscriptionStatus=TranscriptionStatus.QUEUED; created_at:datetime=field(default_factory=lambda:datetime.now(UTC)); task:object|None=None
class SpeechToTextSession(Protocol):
    def results(self)->AsyncIterator[PartialTranscript|FinalTranscript]: ...
    async def cancel(self)->None: ...
class SpeechToTextProvider(Protocol):
    name:str
    async def readiness(self)->bool: ...
    async def start(self,request:TranscriptionRequest)->SpeechToTextSession: ...
class TranscriptionJobRegistry(Protocol):
    async def submit(self,request:TranscriptionRequest)->TranscriptionJob: ...
    async def cancel(self,transcription_id:UUID,connection_id:UUID)->bool: ...
