"""M6 authenticated JSON-only WebSocket ticket and session transport."""
# ruff: noqa: I001

import asyncio
import base64
import json
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from sqlalchemy import select
from tara_api.api.middleware import CORRELATION_HEADER, select_correlation_id
from tara_api.api.v1.auth import authenticated_context
from tara_api.api.v1.tasks import ScheduledTaskResponse
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, ScheduledTaskUpdateCommand, TaskState
from tara_api.persistence.models import ScheduledTaskRunModel
from tara_api.tasks.service import ScheduledTaskService
from tara_api.auth.service import AuthenticationService
from tara_api.config.settings import Settings
from tara_api.domain.audio import AudioFormat
from tara_api.domain.agent import AgentError, AgentInputSource, AgentRequest, AgentState, AgentSubmission, MAX_AGENT_INPUT_CHARS
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.errors import DependencyUnavailableError
from tara_api.domain.transport import ConnectionContext, ConnectionState
from tara_api.transport.audio import MAX_AUDIO_FRAME_BYTES, AudioSession, DeterministicVad, decode_frame
from tara_api.transport.protocol import EventEnvelope, ServerEvent, TransportErrorCode
from tara_api.transport.registry import InMemoryConnectionRegistry
from tara_api.transport.tickets import InMemoryConnectionTicketService
from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import InMemoryTranscriptionJobs
from tara_api.agent.registry import AgentRequestHandle
from tara_api.agent.service import AgentService, AgentServiceFailure
from tara_api.domain.tts import SpeechLanguage, SpeechSynthesisError, SpeechSynthesisState, SynthesisCommand, SynthesisRequestIdentity
from tara_api.tts.registry import SynthesisRequestHandle
from tara_api.tts.service import TextToSpeechService, TextToSpeechServiceFailure
from tara_api.tts.source import InMemoryApprovedAgentResponseSource
from tara_api.domain.wakeword import WakeWordError, WakeWordEvent, WakeWordFailure, WakeWordSessionIdentity, WakeWordState
from tara_api.wakeword.audio import from_m7_audio_frame
from tara_api.wakeword.service import WakeWordService

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger("tara_api")


class TicketResponse(BaseModel):
    ticket: str
    expires_at: str
    protocol_version: int = 1


class AgentRequestEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: StrictStr = Field(min_length=1, max_length=MAX_AGENT_INPUT_CHARS)
    idempotency_key: StrictStr = Field(min_length=1, max_length=256)
    conversation_id: UUID | None = None


class AgentCancelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class TtsCancelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthesis_request_id: UUID


class WakeWordEnableEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransportConnection:
    def __init__(
        self,
        websocket: WebSocket,
        context: ConnectionContext,
        authenticated_context: AuthenticatedOwnerContext,
        agent_service: AgentService,
        tts_service: TextToSpeechService,
        tts_source: InMemoryApprovedAgentResponseSource,
        tts_enabled: bool,
        tts_delivery_timeout_seconds: float,
        wakeword_service: WakeWordService,
    ) -> None:
        self._websocket = websocket
        self.context = context
        self.state = ConnectionState.AUTHENTICATING
        self._next_sequence = 0
        self.last_activity = time.monotonic()
        self._event_times: deque[float] = deque()
        self._closed = False
        self.audio_session: AudioSession | None = None
        self.transcription_jobs: InMemoryTranscriptionJobs | None = None
        self.authenticated_context = authenticated_context
        self.agent_service = agent_service
        self.agent_tasks: set[asyncio.Task[None]] = set()
        self.tts_service = tts_service
        self.tts_source = tts_source
        self.tts_enabled = tts_enabled
        self.tts_delivery_timeout_seconds = tts_delivery_timeout_seconds
        self.tts_tasks: dict[UUID, asyncio.Task[None]] = {}
        self.tts_terminal: set[UUID] = set()
        self.wakeword_service = wakeword_service
        self.wakeword_identity: WakeWordSessionIdentity | None = None
        self.wakeword_enabled = False
        self.wakeword_tasks: set[asyncio.Task[None]] = set()

    async def send_event(self, event_type: str, payload: dict[str, object], sequence: int | None = None) -> None:
        event = ServerEvent(
            session_id=self.context.session_id,
            sequence=self._next_sequence if sequence is None else sequence,
            type=event_type,
            payload=payload,
        )
        if sequence is None:
            self._next_sequence += 1
        await self._websocket.send_text(event.model_dump_json())

    async def close(self, code: int, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        self.state = ConnectionState.CLOSED
        await self._websocket.close(code=code, reason=reason)

    def clear_audio_session(self, canceled: bool = False) -> tuple[UUID, list[str]] | None:
        session = self.audio_session
        if session is None:
            return None
        if canceled:
            session.cancel()
            events: list[str] = []
        else:
            events = session.stop()
        self.audio_session = None
        return session.session_id, events

    def allow_event(self, maximum_per_second: int) -> bool:
        now = time.monotonic()
        while self._event_times and self._event_times[0] <= now - 1:
            self._event_times.popleft()
        if len(self._event_times) >= maximum_per_second:
            return False
        self._event_times.append(now)
        return True


def _ticket_service(request: Request) -> InMemoryConnectionTicketService:
    return cast(InMemoryConnectionTicketService, request.app.state.connection_ticket_service)


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> TicketResponse:
    try:
        ticket, expires_at = await _ticket_service(request).create(context)
    except (RuntimeError, ValueError) as error:
        raise DependencyUnavailableError from error
    return TicketResponse(ticket=ticket, expires_at=expires_at.isoformat())


@router.websocket("/session")
async def websocket_session(websocket: WebSocket, ticket: str | None = None) -> None:
    app = websocket.app
    settings = cast(Settings, app.state.settings)
    ticket_service = cast(InMemoryConnectionTicketService, app.state.connection_ticket_service)
    registry = cast(InMemoryConnectionRegistry, app.state.connection_registry)
    authentication = cast(AuthenticationService, app.state.authentication_service)
    correlation_id = select_correlation_id(websocket.headers.get(CORRELATION_HEADER))
    context = await ticket_service.consume(ticket or "")
    if context is None:
        await websocket.close(code=4401, reason="Authentication failed.")
        _log("websocket_rejected", correlation_id=correlation_id, outcome="authentication_failed")
        return

    connection = TransportConnection(
        websocket,
        ConnectionContext(uuid4(), context.owner.id, context.session.id, 1, websocket_scope_time(), correlation_id),
        context,
        cast(AgentService, app.state.agent_service),
        cast(TextToSpeechService, app.state.tts_service),
        cast(InMemoryApprovedAgentResponseSource, app.state.tts_response_source),
        app.state.tts_provider is not None,
        float(settings.tts_delivery_timeout_seconds),
        cast(WakeWordService, app.state.wakeword_service),
    )
    connection.transcription_jobs = cast(InMemoryTranscriptionJobs, app.state.stt_jobs)
    await websocket.accept()
    if not await registry.register(connection):
        await connection.send_event("session.error", {"code": TransportErrorCode.CONNECTION_LIMIT.value, "message": "Connection limit exceeded."})
        await connection.close(1013, "Connection limit exceeded.")
        return
    _log("websocket_opened", connection=connection, outcome="authenticated")
    try:
        await _run_connection(connection, authentication, settings)
    except WebSocketDisconnect:
        pass
    except Exception:
        connection.state = ConnectionState.FAILED
        logger.exception("websocket_transport_error", extra={"event_data": _event_data(connection, "internal_error")})
        await _send_error_and_close(connection, TransportErrorCode.INTERNAL_ERROR, "Transport error.", 1011)
    finally:
        connection.clear_audio_session(canceled=True)
        await _disable_wakeword(connection, emit_state=False)
        if connection.transcription_jobs is not None:
            await connection.transcription_jobs.cancel_connection(connection.context.connection_id)
        await _cancel_tts_connection(connection)
        await registry.remove(connection.context.connection_id)
        await connection.close(1000, "Closed.")
        _log("websocket_closed", connection=connection, outcome=connection.state.value)


async def _run_connection(connection: TransportConnection, authentication: AuthenticationService, settings: Settings) -> None:
    first_event = await _receive_event(connection, settings.websocket_hello_seconds, settings.websocket_max_message_bytes)
    if first_event is None:
        if connection.state != ConnectionState.AUTHENTICATING:
            return
        await _send_error_and_close(connection, TransportErrorCode.HELLO_TIMEOUT, "Hello timed out.", 1008)
        return
    if isinstance(first_event, bytes) or not _valid_event(first_event, connection, -1, "session.hello") or first_event.payload:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "A valid hello is required.", 1008)
        return
    connection.state = ConnectionState.ACTIVE
    connection.last_activity = time.monotonic()
    await connection.send_event("session.accepted", {"connection_id": str(connection.context.connection_id), "protocol_version": 1})
    last_sequence = first_event.sequence
    while connection.state == ConnectionState.ACTIVE:
        idle_remaining = settings.websocket_idle_seconds - (time.monotonic() - connection.last_activity)
        if idle_remaining <= 0:
            await _send_error_and_close(connection, TransportErrorCode.HELLO_TIMEOUT, "Connection idle timeout.", 1001)
            return
        timeout = min(float(settings.websocket_session_check_seconds), idle_remaining)
        event = await _receive_event(connection, timeout, settings.websocket_max_message_bytes)
        if event is None:
            if connection.state != ConnectionState.ACTIVE:
                return
            if not await authentication.is_owner_session_active(connection.context.owner_id, connection.context.session_id):
                await _cancel_connection_jobs(connection)
                await _send_error_and_close(connection, TransportErrorCode.SESSION_INVALIDATED, "Session is no longer active.", 4401)
                return
            continue
        if isinstance(event, bytes):
            if not await authentication.is_owner_session_active(connection.context.owner_id, connection.context.session_id):
                await _cancel_connection_jobs(connection)
                await _send_error_and_close(connection, TransportErrorCode.SESSION_INVALIDATED, "Session is no longer active.", 4401)
                return
            await _handle_audio_frame(connection, event)
            continue
        if not await authentication.is_owner_session_active(connection.context.owner_id, connection.context.session_id):
            await _cancel_connection_jobs(connection)
            await _send_error_and_close(connection, TransportErrorCode.SESSION_INVALIDATED, "Session is no longer active.", 4401)
            return
        if not connection.allow_event(settings.websocket_max_events_per_second):
            await _send_error_and_close(connection, TransportErrorCode.RATE_LIMITED, "Event rate limit exceeded.", 1008)
            return
        if not _valid_event(event, connection, last_sequence):
            await _send_error_and_close(connection, TransportErrorCode.INVALID_SEQUENCE, "Event sequence is invalid.", 1008)
            return
        last_sequence = event.sequence
        connection.last_activity = time.monotonic()
        if event.type == "session.ping" and not event.payload:
            await connection.send_event("session.pong", {"reply_to": str(event.event_id)})
        elif event.type == "client.ack" and _valid_ack(event.payload):
            await connection.send_event("server.ack", {"reply_to": str(event.payload["event_id"])})
        elif event.type == "session.close" and not event.payload:
            connection.state = ConnectionState.CLOSING
            await connection.send_event("session.closing", {"reason": "Client requested close."})
            await connection.close(1000, "Client requested close.")
        elif event.type == "audio.session.start":
            await _start_audio(connection, event.payload)
        elif event.type == "audio.format":
            await _negotiate_audio(connection, event.payload)
        elif event.type in {"audio.session.stop", "audio.session.cancel"}:
            await _stop_audio(connection, event.type == "audio.session.cancel")
        elif event.type == "audio.flush":
            await _flush_audio(connection)
        elif event.type == "transcript.cancel":
            await _cancel_transcript(connection, event.payload)
        elif event.type == "agent.request":
            await _submit_agent_request(connection, event.payload)
        elif event.type == "agent.cancel":
            await _cancel_agent_request(connection, event.payload)
        elif event.type == "tts.cancel":
            await _cancel_tts_request(connection, event.payload)
        elif event.type == "wakeword.enable":
            await _enable_wakeword(connection, event.payload)
        elif event.type == "wakeword.disable":
            await _disable_wakeword(connection, emit_state=True)
        elif event.type.startswith("task."):
            await _handle_task_command(connection, event.type, event.payload)
        else:
            await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Event is not supported.", 1008)


async def _receive_event(connection: TransportConnection, timeout: float, max_bytes: int) -> EventEnvelope | bytes | None:
    try:
        message = await asyncio.wait_for(connection._websocket.receive(), timeout)  # noqa: SLF001
    except TimeoutError:
        return None
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    raw_bytes = message.get("bytes")
    if isinstance(raw_bytes, bytes):
        if len(raw_bytes) > min(max_bytes, MAX_AUDIO_FRAME_BYTES):
            await _send_error_and_close(connection, TransportErrorCode.PAYLOAD_TOO_LARGE, "Audio frame is too large.", 1009)
            return None
        return raw_bytes
    raw_text = message.get("text")
    if not isinstance(raw_text, str) or len(raw_text.encode("utf-8")) > max_bytes:
        await _send_error_and_close(connection, TransportErrorCode.PAYLOAD_TOO_LARGE, "Message is invalid or too large.", 1009)
        return None
    try:
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict) or parsed.get("protocol_version") != 1:
            await _send_error_and_close(connection, TransportErrorCode.UNSUPPORTED_PROTOCOL, "Protocol version is not supported.", 1002)
            return None
        return EventEnvelope.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError):
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Event is invalid.", 1002)
        return None


def _valid_event(event: EventEnvelope, connection: TransportConnection, previous_sequence: int, required_type: str | None = None) -> bool:
    return event.session_id == connection.context.session_id and event.sequence > previous_sequence and (required_type is None or event.type == required_type)


def _valid_ack(payload: dict[str, Any]) -> bool:
    if set(payload) != {"event_id"}:
        return False
    try:
        UUID(str(payload["event_id"]))
    except (TypeError, ValueError):
        return False
    return True


async def _send_error_and_close(connection: TransportConnection, code: TransportErrorCode, message: str, close_code: int) -> None:
    if connection.state not in {ConnectionState.CLOSING, ConnectionState.CLOSED}:
        await connection.send_event("session.error", {"code": code.value, "message": message})
        connection.state = ConnectionState.CLOSING
        await connection.close(close_code, message)


def websocket_scope_time() -> datetime:
    return datetime.now(UTC)


def _event_data(connection: TransportConnection, outcome: str) -> dict[str, object]:
    return {
        "connection_id": str(connection.context.connection_id),
        "owner_id": str(connection.context.owner_id)[:12],
        "session_id": str(connection.context.session_id)[:12],
        "correlation_id": connection.context.correlation_id,
        "outcome": outcome,
    }


def _log(event: str, connection: TransportConnection | None = None, correlation_id: str | None = None, outcome: str = "") -> None:
    data = _event_data(connection, outcome) if connection else {"correlation_id": correlation_id, "outcome": outcome}
    logger.info(event, extra={"event_data": data})


async def _start_audio(connection: TransportConnection, payload: dict[str, Any]) -> None:
    if set(payload) != {"audio_session_id"} or connection.audio_session is not None:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio session start is invalid.", 1008)
        return
    try:
        connection.audio_session = AudioSession(UUID(str(payload["audio_session_id"])))
    except ValueError:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio session start is invalid.", 1008)
        return
    await connection.send_event("audio.session.accepted", {"audio_session_id": str(connection.audio_session.session_id)})


async def _negotiate_audio(connection: TransportConnection, payload: dict[str, Any]) -> None:
    if connection.audio_session is None or payload != {"sample_rate": 16000, "sample_width_bytes": 2, "channels": 1, "frame_ms": 20}:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio format is unsupported.", 1008)
        return
    try:
        connection.audio_session.negotiate(AudioFormat())
    except ValueError:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio format is unsupported.", 1008)


async def _stop_audio(connection: TransportConnection, canceled: bool) -> None:
    await _disable_wakeword(connection, emit_state=False)
    cleared = connection.clear_audio_session(canceled)
    payload: dict[str, object] = {"canceled": canceled}
    if cleared is not None:
        session_id, events = cleared
        payload["audio_session_id"] = str(session_id)
        for event_type in events:
            await connection.send_event(event_type, {"audio_session_id": str(session_id)})
    await connection.send_event("audio.session.stopped", payload)


async def _flush_audio(connection: TransportConnection) -> None:
    if connection.audio_session is None:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio session is not active.", 1008)
        return
    await _stop_audio(connection, canceled=False)


async def _handle_audio_frame(connection: TransportConnection, data: bytes) -> None:
    if connection.audio_session is None:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio session is not active.", 1008)
        return
    try:
        frame = decode_frame(data)
        events, level = connection.audio_session.ingest(frame, DeterministicVad())
    except ValueError:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Audio frame is invalid.", 1008)
        return
    connection.last_activity = time.monotonic()
    smoothed_level = connection.audio_session.audio_level(level)
    if smoothed_level is not None:
        await connection.send_event("audio.level", {"level": round(smoothed_level, 3)})
    for event_type in events:
        await connection.send_event(event_type, {"audio_session_id": str(connection.audio_session.session_id)})
        if event_type == "vad.speech.started":
            await _cancel_active_tts(connection)
        if event_type == "vad.turn.completed":
            pcm = connection.audio_session.take_completed_pcm()
            if pcm and connection.transcription_jobs is not None:
                request = TranscriptionRequest(uuid4(), connection.context.owner_id, connection.context.session_id, connection.context.connection_id, connection.audio_session.session_id, uuid4(), pcm, datetime.now(UTC))
                try:
                    await connection.transcription_jobs.submit(request)
                except ValueError as error:
                    await connection.send_event("transcript.error", {"audio_session_id": str(connection.audio_session.session_id), "code": str(error)})
    if connection.wakeword_enabled and connection.wakeword_identity is not None:
        task = asyncio.create_task(_process_wakeword_frame(connection, frame))
        connection.wakeword_tasks.add(task)
        task.add_done_callback(connection.wakeword_tasks.discard)


async def _cancel_transcript(connection: TransportConnection, payload: dict[str, Any]) -> None:
    if set(payload) != {"transcription_id"} or connection.transcription_jobs is None:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Transcript cancellation is invalid.", 1008)
        return
    try:
        canceled = await connection.transcription_jobs.cancel(UUID(str(payload["transcription_id"])), connection.context.connection_id, connection.context.owner_id, connection.context.session_id)
    except ValueError:
        canceled = False
    if not canceled:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Transcript cancellation is invalid.", 1008)


async def _cancel_connection_jobs(connection: TransportConnection) -> None:
    if connection.transcription_jobs is not None:
        await connection.transcription_jobs.cancel_connection(connection.context.connection_id)
    await connection.agent_service.cancel_connection(connection.context.connection_id)
    await _cancel_tts_connection(connection)
    await _disable_wakeword(connection, emit_state=False)
    if connection.agent_tasks:
        await asyncio.gather(*tuple(connection.agent_tasks), return_exceptions=True)


async def _enable_wakeword(connection: TransportConnection, payload: dict[str, Any]) -> None:
    try:
        WakeWordEnableEvent.model_validate(payload)
    except ValidationError:
        await _send_wakeword_error(connection, WakeWordError.INVALID_AUDIO_FRAME)
        return
    session = connection.audio_session
    if session is None or not session.format_negotiated:
        await _send_wakeword_error(connection, WakeWordError.MICROPHONE_NOT_ACTIVE)
        return
    identity = WakeWordSessionIdentity(
        connection.context.owner_id,
        connection.context.session_id,
        connection.context.connection_id,
        session.session_id,
    )
    if connection.wakeword_enabled and connection.wakeword_identity == identity:
        await _send_wakeword_state(connection, WakeWordState.LISTENING)
        return
    await _disable_wakeword(connection, emit_state=False)
    try:
        state = await connection.wakeword_service.begin(identity, foreground_active=True)
    except WakeWordFailure as error:
        await _send_wakeword_error(connection, error.code)
        return
    connection.wakeword_identity = identity if state is not WakeWordState.DISABLED else None
    connection.wakeword_enabled = state is not WakeWordState.DISABLED
    await _send_wakeword_state(connection, state)


async def _disable_wakeword(connection: TransportConnection, *, emit_state: bool) -> None:
    identity = connection.wakeword_identity
    connection.wakeword_enabled = False
    connection.wakeword_identity = None
    if identity is not None:
        await connection.wakeword_service.cancel(identity)
    for task in tuple(connection.wakeword_tasks):
        task.cancel()
    if connection.wakeword_tasks:
        await asyncio.gather(*tuple(connection.wakeword_tasks), return_exceptions=True)
    if emit_state and connection.state == ConnectionState.ACTIVE:
        await _send_wakeword_state(connection, WakeWordState.DISABLED)


async def _process_wakeword_frame(connection: TransportConnection, frame: object) -> None:
    identity = connection.wakeword_identity
    if identity is None or connection.state != ConnectionState.ACTIVE:
        return
    from tara_api.domain.audio import AudioFrame

    if not isinstance(frame, AudioFrame):
        return
    try:
        event = await connection.wakeword_service.ingest(
            identity,
            from_m7_audio_frame(identity, frame, datetime.now(UTC)),
            foreground_active=True,
            tts_playing=bool(connection.tts_tasks),
        )
    except asyncio.CancelledError:
        return
    except WakeWordFailure as error:
        if connection.state == ConnectionState.ACTIVE and connection.wakeword_identity == identity:
            await _send_wakeword_error(connection, error.code)
        return
    if event is not None and connection.state == ConnectionState.ACTIVE and connection.wakeword_identity == identity:
        await _send_wakeword_detected(connection, event)


async def _send_wakeword_state(connection: TransportConnection, state: WakeWordState) -> None:
    payload: dict[str, object] = {"state": state.value, "foreground_only": True}
    if connection.wakeword_identity is not None:
        payload["audio_session_id"] = str(connection.wakeword_identity.audio_session_id)
    await connection.send_event("wakeword.state", payload)


async def _send_wakeword_detected(connection: TransportConnection, event: WakeWordEvent) -> None:
    await connection.send_event(
        "wakeword.detected",
        {
            "wake_event_id": str(event.event_id),
            "audio_session_id": str(event.identity.audio_session_id),
            "confidence": round(event.confidence.value, 2),
            "detected_at": event.occurred_at.isoformat(),
            "foreground_only": True,
        },
    )
    await _send_wakeword_state(connection, WakeWordState.COOLDOWN)


async def _send_wakeword_error(connection: TransportConnection, code: WakeWordError) -> None:
    await connection.send_event("wakeword.error", {"code": code.value, "message": "Wake-word detection could not be completed."})


async def _submit_agent_request(connection: TransportConnection, payload: dict[str, Any]) -> None:
    try:
        event = AgentRequestEvent.model_validate(payload)
        submission = AgentSubmission(event.text, AgentInputSource.DIRECT_TEXT, event.idempotency_key, event.conversation_id)
    except (ValidationError, ValueError):
        await _send_agent_error(connection, None, AgentError.EMPTY_INPUT)
        return
    await _begin_agent_request(connection, submission)


async def _cancel_agent_request(connection: TransportConnection, payload: dict[str, Any]) -> None:
    try:
        event = AgentCancelEvent.model_validate(payload)
    except ValidationError:
        await _send_agent_error(connection, None, AgentError.INVALID_CONVERSATION)
        return
    if await connection.agent_service.cancel(
        connection.authenticated_context,
        event.request_id,
        connection_id=connection.context.connection_id,
    ):
        return
    await _send_agent_error(connection, str(event.request_id), AgentError.INVALID_REQUEST_STATE)


async def _begin_agent_request(connection: TransportConnection, submission: AgentSubmission) -> None:
    async def publish_state(request_id: UUID, state: AgentState) -> None:
        if connection.state == ConnectionState.ACTIVE:
            await connection.send_event("agent.state", {"request_id": str(request_id), "state": state.value})

    async def listener(request: AgentRequest, state: AgentState) -> None:
        await publish_state(request.request_id, state)

    try:
        handle = await connection.agent_service.begin(
            connection.authenticated_context,
            submission,
            connection_id=connection.context.connection_id,
            listener=listener,
        )
    except AgentServiceFailure as error:
        await _send_agent_error(connection, None, error.code)
        return
    if not handle.created:
        await _send_agent_error(connection, str(handle.request.request_id), AgentError.DUPLICATE_REQUEST)
        return
    await connection.send_event(
        "agent.started",
        {
            "request_id": str(handle.request.request_id),
            "conversation_id": str(handle.request.conversation_id),
            "source": handle.request.source.value,
        },
    )
    await publish_state(handle.request.request_id, AgentState.QUEUED)
    task = asyncio.create_task(_complete_agent_request(connection, connection.agent_service, handle))
    connection.agent_tasks.add(task)
    task.add_done_callback(connection.agent_tasks.discard)


async def submit_final_transcript(connection: TransportConnection, text: str, transcript_id: UUID) -> None:
    """Start a final-transcript request; partial and terminal STT events never call this."""

    await _begin_agent_request(
        connection,
        AgentSubmission(text, AgentInputSource.FINAL_TRANSCRIPT, source_transcript_id=transcript_id),
    )


async def _complete_agent_request(
    connection: TransportConnection,
    service: AgentService,
    handle: AgentRequestHandle,
) -> None:
    try:
        response = await service.complete(handle)
    except asyncio.CancelledError:
        return
    except Exception:
        if connection.state == ConnectionState.ACTIVE:
            await _send_agent_error(connection, str(handle.request.request_id), AgentError.INTERNAL_AGENT_ERROR)
        return
    if connection.state != ConnectionState.ACTIVE:
        return
    if response.state == AgentState.COMPLETED:
        payload: dict[str, object] = {"request_id": str(response.request_id), "text": response.text}
        if response.model_tier is not None and response.model_tier_reason_code is not None:
            payload["model_tier"] = response.model_tier.value
            payload["model_tier_reason_code"] = response.model_tier_reason_code.value
        await connection.send_event("agent.response", payload)
        if response.error is None:
            await _begin_tts_handoff(connection, handle.request, response)
    elif response.state == AgentState.CANCELED:
        await connection.send_event("agent.canceled", {"request_id": str(response.request_id)})
    else:
        await _send_agent_error(connection, str(response.request_id), response.error or AgentError.INTERNAL_AGENT_ERROR)


async def _send_agent_error(connection: TransportConnection, request_id: str | None, code: AgentError) -> None:
    payload: dict[str, object] = {"code": code.value, "message": "The request could not be completed."}
    if request_id is not None:
        payload["request_id"] = request_id
    await connection.send_event("agent.error", payload)


async def _begin_tts_handoff(connection: TransportConnection, request: AgentRequest, response: object) -> None:
    """Start exactly one internal TTS request from a completed, delivered agent response."""

    if not connection.tts_enabled or connection.state != ConnectionState.ACTIVE:
        return
    from tara_api.domain.agent import AgentResponse

    if not isinstance(response, AgentResponse) or not await connection.tts_source.register(request, response):
        return

    settings = cast(Settings, connection._websocket.app.state.settings)  # noqa: SLF001
    provider = connection.tts_service._provider  # noqa: SLF001
    if provider is None:
        return
    command = SynthesisCommand(
        request.request_id,
        provider.voice,
        _tts_language(settings.tts_language_mode),
        provider.supported_formats[0],
    )

    async def listener(identity: SynthesisRequestIdentity, state: SpeechSynthesisState) -> None:
        if connection.state != ConnectionState.ACTIVE or identity.synthesis_request_id in connection.tts_terminal:
            return
        if state is not SpeechSynthesisState.COMPLETED:
            await connection.send_event("tts.state", {"synthesis_request_id": str(identity.synthesis_request_id), "state": state.value})

    try:
        handle = await connection.tts_service.begin(
            connection.authenticated_context,
            command,
            connection_id=connection.context.connection_id,
            listener=listener,
        )
    except TextToSpeechServiceFailure:
        await connection.tts_source.discard(request.request_id)
        return
    if not handle.created:
        return
    identity = handle.identity
    await connection.send_event(
        "tts.started",
        {
            "synthesis_request_id": str(identity.synthesis_request_id),
            "agent_request_id": str(identity.agent_request_id),
            "conversation_id": str(identity.conversation_id),
            "provider": identity.provider,
            "voice": identity.voice.identifier,
            "format": _format_payload(identity),
        },
    )
    await connection.send_event("tts.state", {"synthesis_request_id": str(identity.synthesis_request_id), "state": SpeechSynthesisState.QUEUED.value})
    task = asyncio.create_task(_complete_tts_delivery(connection, handle))
    connection.tts_tasks[identity.synthesis_request_id] = task
    task.add_done_callback(lambda _task: connection.tts_tasks.pop(identity.synthesis_request_id, None))


def _tts_language(language_mode: str) -> SpeechLanguage:
    return {"en": SpeechLanguage.ENGLISH, "hi": SpeechLanguage.HINDI, "mixed": SpeechLanguage.MIXED}.get(language_mode, SpeechLanguage.MIXED)


def _format_payload(identity: SynthesisRequestIdentity) -> dict[str, object]:
    output = identity.output_format
    return {"encoding": output.encoding.value, "sample_rate": output.sample_rate, "channels": output.channels, "bit_depth": output.bit_depth, "container": output.container.value}


async def _complete_tts_delivery(connection: TransportConnection, handle: SynthesisRequestHandle) -> None:
    request_id = handle.identity.synthesis_request_id
    try:
        completed = await connection.tts_service.complete(handle)
        result = completed.result
        if result is None or connection.state != ConnectionState.ACTIVE or request_id in connection.tts_terminal:
            return
        await _send_tts_event(
            connection,
            "tts.audio.start",
            {
                "synthesis_request_id": str(request_id),
                **_format_payload(handle.identity),
                "total_bytes": len(result.audio),
                "total_chunks": len(result.chunks),
                "duration_ms": result.timing.audio_duration_ms,
                "chunking_mode": "post_synthesis_pcm",
                "streaming_mode": "final_only",
            },
        )
        await asyncio.sleep(0.001)
        delivered_bytes = 0
        for chunk in result.chunks:
            if connection.state != ConnectionState.ACTIVE or request_id in connection.tts_terminal:
                return
            await _send_tts_event(
                connection,
                "tts.audio.chunk",
                {
                    "synthesis_request_id": str(request_id),
                    "sequence": chunk.sequence,
                    "byte_offset": chunk.byte_offset,
                    "byte_length": chunk.byte_length,
                    "final": chunk.is_final,
                    "audio_base64": base64.b64encode(chunk.audio).decode("ascii"),
                },
            )
            delivered_bytes += len(chunk.audio)
            await asyncio.sleep(0.001)
        if connection.state != ConnectionState.ACTIVE or request_id in connection.tts_terminal:
            return
        await _send_tts_event(
            connection,
            "tts.audio.end",
            {
                "synthesis_request_id": str(request_id),
                "delivered_chunks": len(result.chunks),
                "delivered_bytes": delivered_bytes,
                "duration_ms": result.timing.audio_duration_ms,
                "completed_at": result.completed_at.isoformat(),
            },
        )
        connection.tts_terminal.add(request_id)
        await connection.send_event("tts.state", {"synthesis_request_id": str(request_id), "state": SpeechSynthesisState.COMPLETED.value})
    except asyncio.CancelledError:
        return
    except TextToSpeechServiceFailure as error:
        if connection.state != ConnectionState.ACTIVE or request_id in connection.tts_terminal:
            return
        connection.tts_terminal.add(request_id)
        if error.code in {SpeechSynthesisError.REQUEST_CANCELED, SpeechSynthesisError.SESSION_INVALIDATED}:
            await connection.send_event("tts.canceled", {"synthesis_request_id": str(request_id)})
        else:
            await _send_tts_error(connection, request_id, error.code)
    except TimeoutError:
        if connection.state == ConnectionState.ACTIVE and request_id not in connection.tts_terminal:
            connection.tts_terminal.add(request_id)
            await _send_tts_error(connection, request_id, SpeechSynthesisError.PROVIDER_TIMEOUT)


async def _send_tts_event(connection: TransportConnection, event_type: str, payload: dict[str, object]) -> None:
    """Bound direct delivery so a slow connection cannot retain audio indefinitely."""

    async with asyncio.timeout(connection.tts_delivery_timeout_seconds):
        await connection.send_event(event_type, payload)


async def _cancel_tts_request(connection: TransportConnection, payload: dict[str, Any]) -> None:
    try:
        event = TtsCancelEvent.model_validate(payload)
    except ValidationError:
        await _send_tts_error(connection, None, SpeechSynthesisError.INVALID_AGENT_SOURCE)
        return
    request_id = event.synthesis_request_id
    task = connection.tts_tasks.get(request_id)
    canceled = await connection.tts_service.cancel(
        connection.authenticated_context,
        request_id,
        connection_id=connection.context.connection_id,
    )
    if task is not None:
        task.cancel()
        canceled = True
    if not canceled:
        await _send_tts_error(connection, None, SpeechSynthesisError.INVALID_AGENT_SOURCE)
        return
    if request_id not in connection.tts_terminal:
        connection.tts_terminal.add(request_id)
        await connection.send_event("tts.canceled", {"synthesis_request_id": str(request_id)})


async def _cancel_active_tts(connection: TransportConnection) -> None:
    for request_id in tuple(connection.tts_tasks):
        await _cancel_tts_request(connection, {"synthesis_request_id": request_id})


async def _cancel_tts_connection(connection: TransportConnection) -> None:
    for task in tuple(connection.tts_tasks.values()):
        task.cancel()
    await connection.tts_service.cancel_connection(connection.context.connection_id)
    if connection.tts_tasks:
        await asyncio.gather(*tuple(connection.tts_tasks.values()), return_exceptions=True)


async def _send_tts_error(connection: TransportConnection, request_id: UUID | None, code: SpeechSynthesisError) -> None:
    payload: dict[str, object] = {"code": code.value, "message": "Speech synthesis could not be completed."}
    if request_id is not None:
        payload["synthesis_request_id"] = str(request_id)
    await connection.send_event("tts.error", payload)


async def _handle_task_command(connection: TransportConnection, event_type: str, payload: dict[str, Any]) -> None:
    app = connection._websocket.app
    service: ScheduledTaskService = app.state.scheduled_task_service
    context = connection.authenticated_context

    try:
        if event_type == "task.create":
            schedule_raw = payload.get("schedule", {})
            run_at_val = schedule_raw.get("run_at")
            run_at_dt = datetime.fromisoformat(run_at_val) if isinstance(run_at_val, str) else run_at_val
            if run_at_dt.tzinfo is None:
                run_at_dt = run_at_dt.replace(tzinfo=UTC)
            schedule = ScheduleDefinition(
                timezone=schedule_raw.get("timezone", "UTC"),
                run_at=run_at_dt,
                interval_minutes=schedule_raw.get("interval_minutes"),
                occurrence_limit=schedule_raw.get("occurrence_limit"),
            )
            cmd = ScheduledTaskCreateCommand(
                title=payload["title"],
                instruction=payload["instruction"],
                capability_id=payload["capability_id"],
                target=payload["target"],
                parameters=payload.get("parameters", {}),
                schedule=schedule,
                idempotency_key=payload["idempotency_key"],
            )
            task = await service.create(context, cmd)
            resp = ScheduledTaskResponse.from_domain(task).model_dump(mode="json")
            if task.state == TaskState.PENDING_CONFIRMATION:
                await connection.send_event("task.pending_confirmation", resp)
            else:
                await connection.send_event("task.created", resp)

        elif event_type == "task.list":
            tasks = await service.list(context)
            items = [ScheduledTaskResponse.from_domain(t).model_dump(mode="json") for t in tasks]
            await connection.send_event("task.tasks", {"tasks": items})

        elif event_type == "task.get":
            task_id = UUID(payload["task_id"])
            fetched_task = await service.get(context, task_id)
            if fetched_task is None:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.detail", ScheduledTaskResponse.from_domain(fetched_task).model_dump(mode="json"))

        elif event_type == "task.update":
            task_id = UUID(payload["task_id"])
            schedule_def = None
            if "schedule" in payload and payload["schedule"] is not None:
                s_raw = payload["schedule"]
                s_run_at = s_raw.get("run_at")
                s_dt = datetime.fromisoformat(s_run_at) if isinstance(s_run_at, str) else s_run_at
                if s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=UTC)
                schedule_def = ScheduleDefinition(
                    timezone=s_raw.get("timezone", "UTC"),
                    run_at=s_dt,
                    interval_minutes=s_raw.get("interval_minutes"),
                    occurrence_limit=s_raw.get("occurrence_limit"),
                )
            cmd_update = ScheduledTaskUpdateCommand(
                title=payload.get("title"),
                instruction=payload.get("instruction"),
                capability_id=payload.get("capability_id"),
                target=payload.get("target"),
                parameters=payload.get("parameters"),
                schedule=schedule_def,
            )
            updated = await service.update(context, task_id, cmd_update)
            if updated is None:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.updated", ScheduledTaskResponse.from_domain(updated).model_dump(mode="json"))

        elif event_type == "task.pause":
            task_id = UUID(payload["task_id"])
            ok = await service.pause(context, task_id)
            if not ok:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.paused", {"task_id": str(task_id)})

        elif event_type in {"task.resume", "task.enable"}:
            task_id = UUID(payload["task_id"])
            ok = await service.resume(context, task_id)
            if not ok:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.resumed", {"task_id": str(task_id)})

        elif event_type == "task.disable":
            task_id = UUID(payload["task_id"])
            ok = await service.disable(context, task_id)
            if not ok:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.disabled", {"task_id": str(task_id)})

        elif event_type == "task.cancel":
            task_id = UUID(payload["task_id"])
            ok = await service.cancel(context, task_id)
            if not ok:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.canceled", {"task_id": str(task_id)})

        elif event_type == "task.delete":
            task_id = UUID(payload["task_id"])
            ok = await service.delete(context, task_id)
            if not ok:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.deleted", {"task_id": str(task_id)})

        elif event_type == "task.confirm":
            task_id = UUID(payload["task_id"])
            resp_str = payload.get("response", "yes")
            approved = await service.approve_confirmation(context, task_id, resp_str)
            if approved is None:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                await connection.send_event("task.confirmed", ScheduledTaskResponse.from_domain(approved).model_dump(mode="json"))

        elif event_type == "task.runs.list":
            task_id = UUID(payload["task_id"])
            existing_task = await service.get(context, task_id)
            if existing_task is None:
                await connection.send_event("task.error", {"code": "task_not_found", "message": "Task not found"})
            else:
                async with app.state.database.session() as database_session:
                    runs = list(
                        (
                            await database_session.scalars(
                                select(ScheduledTaskRunModel)
                                .where(
                                    ScheduledTaskRunModel.task_id == task_id,
                                    ScheduledTaskRunModel.owner_id == context.owner.id,
                                )
                                .order_by(ScheduledTaskRunModel.claimed_at.desc())
                            )
                        ).all()
                    )
                run_items = [
                    {
                        "id": str(r.id),
                        "run_id": str(r.run_id),
                        "task_id": str(r.task_id),
                        "scheduled_for": r.scheduled_for.isoformat(),
                        "claimed_at": r.claimed_at.isoformat(),
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                        "state": r.state,
                        "outcome_code": r.outcome_code,
                        "error_code": r.error_code,
                    }
                    for r in runs
                ]
                await connection.send_event("task.runs", {"task_id": str(task_id), "runs": run_items})
    except Exception as exc:
        await connection.send_event("task.error", {"code": "invalid_command", "message": str(exc)})
