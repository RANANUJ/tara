"""Framework-independent M6 WebSocket ticket and connection contracts."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from tara_api.domain.auth import AuthenticatedOwnerContext


class ConnectionState(StrEnum):
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ConnectionContext:
    connection_id: UUID
    owner_id: UUID
    session_id: UUID
    protocol_version: int
    connected_at: datetime
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionTicket:
    ticket_hash: str
    owner_id: UUID
    session_id: UUID
    expires_at: datetime


class WebSocketConnection(Protocol):
    context: ConnectionContext
    state: ConnectionState

    async def send_event(self, event_type: str, payload: dict[str, object], sequence: int) -> None: ...

    async def close(self, code: int, reason: str) -> None: ...


class ConnectionRegistry(Protocol):
    async def register(self, connection: WebSocketConnection) -> bool: ...

    async def get(self, connection_id: UUID) -> WebSocketConnection | None: ...

    async def list_for_owner(self, owner_id: UUID) -> tuple[ConnectionContext, ...]: ...

    async def remove(self, connection_id: UUID) -> None: ...


class ConnectionTicketService(Protocol):
    async def create(self, context: AuthenticatedOwnerContext) -> tuple[str, datetime]: ...

    async def consume(self, raw_ticket: str) -> AuthenticatedOwnerContext | None: ...


class WebSocketEventPublisher(Protocol):
    async def publish_to_connection(self, owner_id: UUID, session_id: UUID, connection_id: UUID, event_type: str, payload: dict[str, object]) -> bool: ...
