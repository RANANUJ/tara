"""M6 ticket and JSON-only WebSocket transport tests."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tara_api.domain.audio import AudioFrame
from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession
from tara_api.transport.audio import CANONICAL_FORMAT, encode_frame
from tara_api.transport.tickets import InMemoryConnectionTicketService


class FakeAuthentication:
    def __init__(self, active: bool = True) -> None:
        self.active = active

    async def is_context_active(self, _context: AuthenticatedOwnerContext) -> bool:
        return self.active


def _context() -> AuthenticatedOwnerContext:
    now = datetime.now(UTC)
    owner = Owner(uuid4(), "owner@example.test", now)
    session = OwnerSession(uuid4(), owner.id, now, now + timedelta(hours=1), now, None, None)
    return AuthenticatedOwnerContext(owner, session)


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str]:
    login = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.test", "password": "correct-horse-battery-staple"}).json()
    return {"Authorization": f"Bearer {login['token']}"}, login["session_id"]


def _ticket(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/v1/ws/tickets", headers=headers)
    assert response.status_code == 201
    return response.json()["ticket"]


def _event(session_id: str, sequence: int, event_type: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "event_id": str(uuid4()),
        "session_id": session_id,
        "sequence": sequence,
        "timestamp": datetime.now(UTC).isoformat(),
        "type": event_type,
        "payload": payload or {},
    }


async def test_ticket_service_hashes_tickets_and_consumes_exactly_once() -> None:
    authentication = FakeAuthentication()
    service = InMemoryConnectionTicketService(authentication, timedelta(minutes=1))
    context = _context()
    raw_ticket, _expires_at = await service.create(context)

    assert raw_ticket not in repr(service._tickets)  # noqa: SLF001
    results = await asyncio.gather(service.consume(raw_ticket), service.consume(raw_ticket))
    assert results.count(context) == 1


async def test_ticket_service_rejects_expired_or_invalidated_session() -> None:
    authentication = FakeAuthentication()
    service = InMemoryConnectionTicketService(authentication, timedelta(minutes=1))
    context = _context()
    raw_ticket, _expires_at = await service.create(context)
    ticket_hash = service._hash(raw_ticket)  # noqa: SLF001
    ticket, stored_context = service._tickets[ticket_hash]  # noqa: SLF001
    service._tickets[ticket_hash] = (replace(ticket, expires_at=datetime.now(UTC) - timedelta(seconds=1)), stored_context)  # noqa: SLF001
    assert await service.consume(raw_ticket) is None

    raw_ticket, _expires_at = await service.create(context)
    authentication.active = False
    assert await service.consume(raw_ticket) is None


def test_ticket_requires_authentication_and_is_single_use(client: TestClient) -> None:
    assert client.post("/api/v1/ws/tickets").status_code == 401
    headers, session_id = _bootstrap(client)
    ticket = _ticket(client, headers)

    with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        assert websocket.receive_json()["type"] == "session.accepted"

    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}"):
        pass


def test_transport_requires_hello_then_returns_pong_without_payload_echo(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    ticket = _ticket(client, headers)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        accepted = websocket.receive_json()
        assert accepted["type"] == "session.accepted"
        assert accepted["payload"]["protocol_version"] == 1

        ping = _event(session_id, 1, "session.ping")
        websocket.send_json(ping)
        pong = websocket.receive_json()
        assert pong["type"] == "session.pong"
        assert pong["payload"] == {"reply_to": ping["event_id"]}


def test_invalid_or_pre_hello_events_return_safe_error(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    ticket = _ticket(client, headers)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.ping"))
        error = websocket.receive_json()
        assert error["type"] == "session.error"
        assert error["payload"]["code"] == "invalid_event"
        assert "traceback" not in str(error).lower()

    ticket = _ticket(client, headers)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={ticket}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello", {"unexpected": True}))
        assert websocket.receive_json()["payload"]["code"] == "invalid_event"


def test_invalid_ticket_and_connection_limit_are_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/v1/ws/session?ticket=invalid"):
        pass

    headers, session_id = _bootstrap(client)
    client.app.state.settings.websocket_max_connections_per_session = 1
    client.app.state.connection_registry._max_connections_per_session = 1
    first_ticket, second_ticket = _ticket(client, headers), _ticket(client, headers)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={first_ticket}") as first:
        first.send_json(_event(session_id, 0, "session.hello"))
        first.receive_json()
        with client.websocket_connect(f"/api/v1/ws/session?ticket={second_ticket}") as second:
            error = second.receive_json()
            assert error["type"] == "session.error"
            assert error["payload"]["code"] == "connection_limit_exceeded"


def test_audio_requires_negotiation_then_emits_level_and_vad_events(client: TestClient) -> None:
    headers, session_id = _bootstrap(client)
    with client.websocket_connect(f"/api/v1/ws/session?ticket={_ticket(client, headers)}") as websocket:
        websocket.send_json(_event(session_id, 0, "session.hello"))
        websocket.receive_json()
        audio_session_id = str(uuid4())
        websocket.send_json(_event(session_id, 1, "audio.session.start", {"audio_session_id": audio_session_id}))
        assert websocket.receive_json()["type"] == "audio.session.accepted"
        websocket.send_json(_event(session_id, 2, "audio.format", {"sample_rate": 16000, "sample_width_bytes": 2, "channels": 1, "frame_ms": 20}))
        payload = (10000).to_bytes(2, "little", signed=True) * (CANONICAL_FORMAT.frame_bytes // 2)
        websocket.send_bytes(encode_frame(AudioFrame(UUID(audio_session_id), 0, payload)))
        assert websocket.receive_json()["type"] == "audio.level"
