"""Framework-independent single-owner authentication contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Owner:
    id: UUID
    email: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OwnerCredential:
    owner: Owner
    password_hash: str


@dataclass(frozen=True, slots=True)
class OwnerSession:
    id: UUID
    owner_id: UUID
    issued_at: datetime
    expires_at: datetime
    last_used_at: datetime
    revoked_at: datetime | None
    client_label: str | None


@dataclass(frozen=True, slots=True)
class AuthenticatedOwnerContext:
    owner: Owner
    session: OwnerSession


class OwnerRepository(Protocol):
    async def bootstrap(self, email: str, password_hash: str) -> Owner | None: ...

    async def bootstrap_required(self) -> bool: ...

    async def get_by_email(self, email: str) -> OwnerCredential | None: ...

    async def record_login_audit(self, outcome: str, occurred_at: datetime) -> None: ...


class SessionRepository(Protocol):
    async def create(self, owner_id: UUID, token_hash: str, expires_at: datetime, client_label: str | None) -> OwnerSession: ...

    async def authenticate(self, token_hash: str, now: datetime) -> AuthenticatedOwnerContext | None: ...

    async def is_active(self, owner_id: UUID, session_id: UUID, now: datetime) -> OwnerSession | None: ...

    async def revoke(self, owner_id: UUID, session_id: UUID, now: datetime) -> bool: ...

    async def revoke_all(self, owner_id: UUID, now: datetime) -> None: ...

    async def list_for_owner(self, owner_id: UUID) -> list[OwnerSession]: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...


class SessionTokenGenerator(Protocol):
    def generate(self) -> str: ...

    def hash(self, token: str) -> str: ...


class LoginRateLimiter(Protocol):
    def allowed(self, key: str, now: datetime) -> bool: ...

    def record_failure(self, key: str, now: datetime) -> None: ...

    def reset(self, key: str) -> None: ...
