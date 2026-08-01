"""M6 authenticated JSON-only WebSocket ticket and session transport."""
# ruff: noqa: I001

import asyncio
import json
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError

from tara_api.api.middleware import CORRELATION_HEADER, select_correlation_id
from tara_api.api.v1.auth import authenticated_context
from tara_api.auth.service import AuthenticationService
from tara_api.config.settings import Settings
from tara_api.domain.audio import AudioFormat
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.errors import DependencyUnavailableError
from tara_api.domain.transport import ConnectionContext, ConnectionState
from tara_api.transport.audio import MAX_AUDIO_FRAME_BYTES, AudioSession, DeterministicVad, decode_frame
from tara_api.transport.protocol import EventEnvelope, ServerEvent, TransportErrorCode
from tara_api.transport.registry import InMemoryConnectionRegistry
from tara_api.transport.tickets import InMemoryConnectionTicketService
from tara_api.domain.stt import TranscriptionRequest
from tara_api.stt.service import InMemoryTranscriptionJobs

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger("tara_api")


class TicketResponse(BaseModel):
    ticket: str
    expires_at: str
    protocol_version: int = 1


class TransportConnection:
    def __init__(self, websocket: WebSocket, context: ConnectionContext) -> None:
        self._websocket = websocket
        self.context = context
        self.state = ConnectionState.AUTHENTICATING
        self._next_sequence = 0
        self.last_activity = time.monotonic()
        self._event_times: deque[float] = deque()
        self._closed = False
        self.audio_session: AudioSession | None = None
        self.transcription_jobs: InMemoryTranscriptionJobs | None = None

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
    )
    async def publish_transcript(job: object, event_type: str, payload: dict[str, object]) -> None:
        request = cast(TranscriptionRequest, cast(Any, job).request)
        await connection.send_event(event_type, {"transcription_id": str(request.transcription_id), "audio_session_id": str(request.audio_session_id), "turn_id": str(request.turn_id), **payload})
    connection.transcription_jobs = InMemoryTranscriptionJobs(app.state.stt_provider, publish_transcript, settings.stt_max_queued_jobs, settings.stt_max_concurrent_jobs, settings.stt_timeout_seconds)
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
                await _send_error_and_close(connection, TransportErrorCode.SESSION_INVALIDATED, "Session is no longer active.", 4401)
                return
            continue
        if isinstance(event, bytes):
            if not await authentication.is_owner_session_active(connection.context.owner_id, connection.context.session_id):
                await _send_error_and_close(connection, TransportErrorCode.SESSION_INVALIDATED, "Session is no longer active.", 4401)
                return
            await _handle_audio_frame(connection, event)
            continue
        if not await authentication.is_owner_session_active(connection.context.owner_id, connection.context.session_id):
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
        if event_type == "vad.turn.completed":
            pcm = connection.audio_session.take_completed_pcm()
            if pcm and connection.transcription_jobs is not None:
                request = TranscriptionRequest(uuid4(), connection.context.owner_id, connection.context.session_id, connection.context.connection_id, connection.audio_session.session_id, uuid4(), pcm, datetime.now(UTC))
                try:
                    await connection.transcription_jobs.submit(request)
                except ValueError as error:
                    await connection.send_event("transcript.error", {"audio_session_id": str(connection.audio_session.session_id), "code": str(error)})


async def _cancel_transcript(connection: TransportConnection, payload: dict[str, Any]) -> None:
    if set(payload) != {"transcription_id"} or connection.transcription_jobs is None:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Transcript cancellation is invalid.", 1008)
        return
    try:
        canceled = await connection.transcription_jobs.cancel(UUID(str(payload["transcription_id"])), connection.context.connection_id)
    except ValueError:
        canceled = False
    if not canceled:
        await _send_error_and_close(connection, TransportErrorCode.INVALID_EVENT, "Transcript cancellation is invalid.", 1008)
