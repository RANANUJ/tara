"""Deterministic fixtures for M10B TTS service tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from tara_api.domain.tts import (
    ApprovedAgentResponse,
    SpeechFormat,
    SpeechLanguage,
    SpeechSynthesisError,
    SpeechSynthesisFailure,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechVoice,
    SynthesisCommand,
)
from tara_api.tts.registry import SynthesisRequestRegistry
from tara_api.tts.service import TextToSpeechService
from tara_api.tts.validation import validated_result


class ActiveSessions:
    def __init__(self) -> None:
        self.active: set[tuple[UUID, UUID]] = set()

    async def is_owner_session_active(self, owner_id: UUID, session_id: UUID) -> bool:
        return (owner_id, session_id) in self.active


class ResponseSource:
    def __init__(self) -> None:
        self.responses: dict[UUID, ApprovedAgentResponse] = {}

    async def resolve_completed_response(self, *, owner_id: UUID, session_id: UUID, connection_id: UUID | None, agent_request_id: UUID, assistant_turn_id: UUID | None) -> ApprovedAgentResponse | None:
        response = self.responses.get(agent_request_id)
        if response is None:
            return None
        if (response.owner_id, response.session_id, response.connection_id, response.assistant_turn_id) != (owner_id, session_id, connection_id, assistant_turn_id):
            return None
        return response


class CountingProvider:
    name = "test-provider"
    streaming_supported = False

    def __init__(self, *, delay_seconds: float = 0, failure: SpeechSynthesisError | None = None, audio_bytes: int = 8) -> None:
        self.voice = SpeechVoice("local-voice")
        self.supported_formats = (SpeechFormat(),)
        self.supported_languages = (SpeechLanguage.ENGLISH,)
        self.delay_seconds = delay_seconds
        self.failure = failure
        self.audio_bytes = audio_bytes
        self.calls = 0
        self.running = 0
        self.maximum_running = 0

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        import asyncio

        self.calls += 1
        self.running += 1
        self.maximum_running = max(self.maximum_running, self.running)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            if self.failure is not None:
                raise SpeechSynthesisFailure(self.failure)
            return validated_result(request, b"\0" * self.audio_bytes, synthesis_duration_ms=1)
        finally:
            self.running -= 1

    async def readiness(self):  # type: ignore[no-untyped-def]
        from tara_api.domain.tts import SpeechProviderReadiness, SpeechProviderState

        return SpeechProviderReadiness(True, SpeechProviderState.READY)


def context(owner_id: UUID | None = None, session_id: UUID | None = None) -> AuthenticatedOwnerContext:
    now = datetime.now(UTC)
    owner = Owner(owner_id or uuid4(), "owner@example.test", now)
    return AuthenticatedOwnerContext(owner, OwnerSession(session_id or uuid4(), owner.id, now, now + timedelta(days=1), now, None, None))


def registry(**overrides: int) -> SynthesisRequestRegistry:
    values = {
        "maximum_queued": 8,
        "maximum_concurrent": 1,
        "maximum_per_connection": 2,
        "maximum_per_session": 4,
        "maximum_per_owner": 8,
        "maximum_terminal_records": 8,
        "maximum_retained_audio_bytes": 1024,
    }
    values.update(overrides)
    return SynthesisRequestRegistry(**values, terminal_retention=timedelta(minutes=5))


def response(
    source: ResponseSource,
    owner_context: AuthenticatedOwnerContext,
    *,
    connection_id: UUID | None = None,
    text: str = "Approved final response",
    state: str = "completed",
    agent_request_id: UUID | None = None,
) -> ApprovedAgentResponse:
    item = ApprovedAgentResponse(agent_request_id or uuid4(), owner_context.owner.id, owner_context.session.id, connection_id, uuid4(), text, datetime.now(UTC), uuid4(), state)
    source.responses[item.agent_request_id] = item
    return item


def command(item: ApprovedAgentResponse) -> SynthesisCommand:
    return SynthesisCommand(item.agent_request_id, SpeechVoice("local-voice"), SpeechLanguage.ENGLISH, SpeechFormat(), item.assistant_turn_id)


def service(active_sessions: ActiveSessions, source: ResponseSource, provider: CountingProvider | None, **limits: int | float) -> TextToSpeechService:
    items = registry(**{key: value for key, value in limits.items() if key.startswith("maximum_") and isinstance(value, int)})
    return TextToSpeechService(
        registry=items,
        provider=provider,
        session_validator=active_sessions,
        response_source=source,
        timeout_seconds=float(limits.get("timeout_seconds", 1)),
        maximum_chunk_bytes=int(limits.get("maximum_chunk_bytes", 4)),
    )
