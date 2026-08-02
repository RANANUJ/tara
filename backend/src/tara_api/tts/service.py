"""Framework-independent M10B final-agent-response TTS service."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.tts import (
    ApprovedAgentResponse,
    ApprovedAgentResponseSource,
    SpeechSessionValidator,
    SpeechSynthesisError,
    SpeechSynthesisFailure,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechSynthesisState,
    SynthesisCommand,
    SynthesisRequestIdentity,
    SynthesisServiceResult,
    TextToSpeechProvider,
)
from tara_api.tts.chunking import chunk_synthesized_audio
from tara_api.tts.registry import SynthesisJob, SynthesisLifecycleListener, SynthesisRequestHandle, SynthesisRequestRegistry
from tara_api.tts.validation import normalize_synthesis_text, validated_result


class TextToSpeechServiceFailure(RuntimeError):
    """Stable code and generic message for M10B service rejection."""

    def __init__(self, code: SpeechSynthesisError) -> None:
        super().__init__("Speech synthesis could not be completed.")
        self.code = code


class TextToSpeechService:
    """Create bounded TTS jobs only from server-resolved completed M9 responses."""

    def __init__(
        self,
        *,
        registry: SynthesisRequestRegistry,
        provider: TextToSpeechProvider | None,
        session_validator: SpeechSessionValidator,
        response_source: ApprovedAgentResponseSource,
        timeout_seconds: float,
        maximum_chunk_bytes: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if timeout_seconds <= 0 or maximum_chunk_bytes < 2 or maximum_chunk_bytes % 2:
            raise ValueError("invalid TTS service configuration")
        self._registry = registry
        self._provider = provider
        self._session_validator = session_validator
        self._response_source = response_source
        self._timeout_seconds = timeout_seconds
        self._maximum_chunk_bytes = maximum_chunk_bytes
        self._now = now

    async def begin(
        self,
        context: AuthenticatedOwnerContext,
        command: SynthesisCommand,
        *,
        connection_id: UUID | None = None,
        listener: SynthesisLifecycleListener | None = None,
    ) -> SynthesisRequestHandle:
        if not await self._session_validator.is_owner_session_active(context.owner.id, context.session.id):
            raise TextToSpeechServiceFailure(SpeechSynthesisError.SESSION_INVALIDATED)
        if self._provider is None:
            raise TextToSpeechServiceFailure(SpeechSynthesisError.PROVIDER_NOT_CONFIGURED)
        source = await self._response_source.resolve_completed_response(
            owner_id=context.owner.id,
            session_id=context.session.id,
            connection_id=connection_id,
            agent_request_id=command.agent_request_id,
            assistant_turn_id=command.assistant_turn_id,
        )
        self._validate_source(source, context, command, connection_id)
        assert source is not None
        try:
            text = normalize_synthesis_text(source.text)
        except SpeechSynthesisFailure as error:
            raise TextToSpeechServiceFailure(error.code) from error
        identity = SynthesisRequestIdentity(
            uuid4(),
            context.owner.id,
            context.session.id,
            connection_id,
            source.conversation_id,
            source.agent_request_id,
            source.assistant_turn_id,
            self._idempotency_hash(source, command),
            self._provider.name,
            command.voice,
            command.language,
            command.output_format,
            self._utc_now(),
        )
        provider_request = SpeechSynthesisRequest(
            identity.synthesis_request_id,
            identity.owner_id,
            identity.session_id,
            text,
            identity.voice,
            identity.language,
            identity.output_format,
            identity.created_at,
        )
        try:
            return await self._registry.begin(identity, provider_request, self._execute, listener=listener)
        except ValueError as error:
            raise TextToSpeechServiceFailure(self._error_from_value(error)) from error

    async def submit(self, context: AuthenticatedOwnerContext, command: SynthesisCommand, *, connection_id: UUID | None = None) -> SynthesisServiceResult:
        return await self.complete(await self.begin(context, command, connection_id=connection_id))

    async def complete(self, handle: SynthesisRequestHandle) -> SynthesisServiceResult:
        record = await self._registry.wait(handle)
        if record.state != SpeechSynthesisState.COMPLETED:
            raise TextToSpeechServiceFailure(record.error or SpeechSynthesisError.INTERNAL_TTS_ERROR)
        result = await self._registry.consume_audio(
            record.identity.synthesis_request_id,
            owner_id=record.identity.owner_id,
            session_id=record.identity.session_id,
            connection_id=record.identity.connection_id,
        )
        return SynthesisServiceResult(record, result)

    async def cancel(self, context: AuthenticatedOwnerContext, synthesis_request_id: UUID, *, connection_id: UUID | None = None) -> bool:
        if not await self._session_validator.is_owner_session_active(context.owner.id, context.session.id):
            return False
        return await self._registry.cancel(
            synthesis_request_id,
            owner_id=context.owner.id,
            session_id=context.session.id,
            connection_id=connection_id,
        )

    async def cancel_connection(self, connection_id: UUID) -> None:
        await self._registry.cancel_connection(connection_id)

    async def cancel_session(self, owner_id: UUID, session_id: UUID) -> None:
        await self._registry.cancel_session(owner_id, session_id)

    async def cleanup(self) -> None:
        await self._registry.cleanup()

    async def shutdown(self) -> None:
        await self._registry.shutdown()

    async def _execute(self, job: SynthesisJob) -> SpeechSynthesisResult:
        request = job.provider_request
        if request is None or self._provider is None:
            raise SpeechSynthesisFailure(SpeechSynthesisError.PROVIDER_NOT_CONFIGURED)
        if not await self._session_validator.is_owner_session_active(request.owner_id, request.session_id):
            raise SpeechSynthesisFailure(SpeechSynthesisError.SESSION_INVALIDATED)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._registry.transition(request.synthesis_id, SpeechSynthesisState.PREPARING)
                await self._registry.transition(request.synthesis_id, SpeechSynthesisState.SYNTHESIZING)
                result = await self._provider.synthesize(request)
                await self._registry.transition(request.synthesis_id, SpeechSynthesisState.CHUNKING)
                chunks = chunk_synthesized_audio(result, min(self._maximum_chunk_bytes, len(result.audio)))
                await asyncio.sleep(0)
                return validated_result(
                    request,
                    result.audio,
                    synthesis_duration_ms=result.timing.synthesis_duration_ms,
                    completed_at=result.completed_at,
                    chunks=chunks,
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            raise SpeechSynthesisFailure(SpeechSynthesisError.REQUEST_TIMED_OUT) from error

    @staticmethod
    def _validate_source(source: ApprovedAgentResponse | None, context: AuthenticatedOwnerContext, command: SynthesisCommand, connection_id: UUID | None) -> None:
        if source is None:
            raise TextToSpeechServiceFailure(SpeechSynthesisError.INVALID_AGENT_SOURCE)
        if source.state != "completed":
            raise TextToSpeechServiceFailure(SpeechSynthesisError.SOURCE_NOT_COMPLETED)
        if (
            source.agent_request_id != command.agent_request_id
            or source.assistant_turn_id != command.assistant_turn_id
            or source.owner_id != context.owner.id
            or source.session_id != context.session.id
            or source.connection_id != connection_id
        ):
            raise TextToSpeechServiceFailure(SpeechSynthesisError.INVALID_AGENT_SOURCE)

    def _utc_now(self) -> datetime:
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("TTS clock must be UTC")
        return now.astimezone(UTC)

    def _idempotency_hash(self, source: ApprovedAgentResponse, command: SynthesisCommand) -> str:
        values = (
            str(source.agent_request_id),
            str(source.assistant_turn_id),
            self._provider.name if self._provider else "",
            command.voice.identifier,
            command.language.value,
            command.output_format.encoding.value,
            str(command.output_format.sample_rate),
            str(command.output_format.channels),
        )
        value = "|".join(values)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _error_from_value(error: ValueError) -> SpeechSynthesisError:
        try:
            return SpeechSynthesisError(str(error))
        except ValueError:
            return SpeechSynthesisError.INTERNAL_TTS_ERROR
