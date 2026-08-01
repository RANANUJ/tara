"""Concurrency-safe in-memory registry for active M6 transport connections."""

import asyncio
from uuid import UUID

from tara_api.domain.transport import ConnectionContext, WebSocketConnection


class InMemoryConnectionRegistry:
    def __init__(self, max_connections_per_session: int) -> None:
        if max_connections_per_session <= 0:
            raise ValueError("max_connections_per_session must be positive")
        self._max_connections_per_session = max_connections_per_session
        self._connections: dict[UUID, WebSocketConnection] = {}
        self._lock = asyncio.Lock()

    async def register(self, connection: WebSocketConnection) -> bool:
        async with self._lock:
            active = sum(1 for item in self._connections.values() if item.context.session_id == connection.context.session_id)
            if active >= self._max_connections_per_session:
                return False
            self._connections[connection.context.connection_id] = connection
            return True

    async def get(self, connection_id: UUID) -> WebSocketConnection | None:
        async with self._lock:
            return self._connections.get(connection_id)

    async def list_for_owner(self, owner_id: UUID) -> tuple[ConnectionContext, ...]:
        async with self._lock:
            return tuple(item.context for item in self._connections.values() if item.context.owner_id == owner_id)

    async def remove(self, connection_id: UUID) -> None:
        async with self._lock:
            self._connections.pop(connection_id, None)


class RegistryEventPublisher:
    def __init__(self, registry: InMemoryConnectionRegistry) -> None:
        self._registry = registry

    async def publish_to_connection(
        self,
        owner_id: UUID,
        session_id: UUID,
        connection_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> bool:
        connection = await self._registry.get(connection_id)
        if connection is None or connection.context.owner_id != owner_id or connection.context.session_id != session_id:
            return False
        await connection.send_event(event_type, payload, 0)
        return True
