"""Bounded in-memory, hash-only WebSocket connection tickets."""

import asyncio
import re
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol

from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.transport import ConnectionTicket

_TICKET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class SessionContextValidator(Protocol):
    async def is_context_active(self, context: AuthenticatedOwnerContext) -> bool: ...


class InMemoryConnectionTicketService:
    def __init__(self, authentication: SessionContextValidator, ttl: timedelta, capacity: int = 1024) -> None:
        if ttl.total_seconds() <= 0 or capacity <= 0:
            raise ValueError("ticket ttl and capacity must be positive")
        self._authentication = authentication
        self._ttl = ttl
        self._capacity = capacity
        self._tickets: dict[str, tuple[ConnectionTicket, AuthenticatedOwnerContext]] = {}
        self._lock = asyncio.Lock()

    async def create(self, context: AuthenticatedOwnerContext) -> tuple[str, datetime]:
        if not await self._authentication.is_context_active(context):
            raise ValueError("inactive session")
        now = datetime.now(UTC)
        raw_ticket = secrets.token_urlsafe(32)
        ticket_hash = self._hash(raw_ticket)
        expires_at = now + self._ttl
        async with self._lock:
            self._purge(now)
            if len(self._tickets) >= self._capacity:
                raise RuntimeError("ticket capacity exceeded")
            self._tickets[ticket_hash] = (ConnectionTicket(ticket_hash, context.owner.id, context.session.id, expires_at), context)
        return raw_ticket, expires_at

    async def consume(self, raw_ticket: str) -> AuthenticatedOwnerContext | None:
        if not _TICKET_PATTERN.fullmatch(raw_ticket):
            return None
        now = datetime.now(UTC)
        async with self._lock:
            self._purge(now)
            stored = self._tickets.pop(self._hash(raw_ticket), None)
        if stored is None:
            return None
        ticket, context = stored
        if ticket.expires_at <= now or not await self._authentication.is_context_active(context):
            return None
        return context

    @staticmethod
    def _hash(raw_ticket: str) -> str:
        return sha256(raw_ticket.encode("utf-8")).hexdigest()

    def _purge(self, now: datetime) -> None:
        for ticket_hash, (ticket, _context) in tuple(self._tickets.items()):
            if ticket.expires_at <= now:
                self._tickets.pop(ticket_hash, None)
