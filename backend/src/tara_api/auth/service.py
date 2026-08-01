"""Single-owner authentication use cases independent of FastAPI and ORM models."""

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from tara_api.domain.auth import (
    AuthenticatedOwnerContext,
    LoginRateLimiter,
    Owner,
    OwnerRepository,
    OwnerSession,
    PasswordHasher,
    SessionRepository,
    SessionTokenGenerator,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthenticationError(RuntimeError):
    pass


class BootstrapClosedError(RuntimeError):
    pass


class AuthenticationService:
    def __init__(
        self,
        owners: OwnerRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: SessionTokenGenerator,
        limiter: LoginRateLimiter,
        now: Callable[[], datetime],
        session_ttl: timedelta,
        idle_ttl: timedelta,
    ) -> None:
        self._owners, self._sessions, self._hasher, self._tokens, self._limiter, self._now = owners, sessions, hasher, tokens, limiter, now
        self._session_ttl, self._idle_ttl = session_ttl, idle_ttl
        self._fake_hash = hasher.hash("not-a-real-password")

    @staticmethod
    def normalize_email(email: str) -> str:
        normalized = email.strip().casefold()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("invalid email")
        return normalized

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 12 or len(password) > 128 or password.isspace():
            raise ValueError("password does not meet policy")

    async def bootstrap_required(self) -> bool:
        return await self._owners.bootstrap_required()

    async def bootstrap(self, email: str, password: str) -> Owner:
        normalized = self.normalize_email(email)
        self.validate_password(password)
        owner = await self._owners.bootstrap(normalized, self._hasher.hash(password))
        if owner is None:
            raise BootstrapClosedError
        return owner

    async def login(self, email: str, password: str, client_label: str | None = None) -> tuple[Owner, OwnerSession, str]:
        now = self._now()
        try:
            normalized = self.normalize_email(email)
        except ValueError:
            normalized = "invalid@example.invalid"
        rate_limit_key = sha256(normalized.encode("utf-8")).hexdigest()
        if not self._limiter.allowed(rate_limit_key, now):
            await self._owners.record_login_audit("rate_limited", now)
            raise AuthenticationError
        credential = await self._owners.get_by_email(normalized)
        password_hash = credential.password_hash if credential else self._fake_hash
        if credential is None or not self._hasher.verify(password_hash, password):
            self._limiter.record_failure(rate_limit_key, now)
            await self._owners.record_login_audit("failed", now)
            raise AuthenticationError
        token = self._tokens.generate()
        session = await self._sessions.create(credential.owner.id, self._tokens.hash(token), now + self._session_ttl, client_label)
        self._limiter.reset(rate_limit_key)
        await self._owners.record_login_audit("succeeded", now)
        return credential.owner, session, token

    async def authenticate(self, token: str) -> AuthenticatedOwnerContext:
        context = await self._sessions.authenticate(self._tokens.hash(token), self._now())
        if context is None:
            raise AuthenticationError
        if context.session.last_used_at + self._idle_ttl <= self._now():
            raise AuthenticationError
        return context

    async def is_context_active(self, context: AuthenticatedOwnerContext) -> bool:
        return await self.is_owner_session_active(context.owner.id, context.session.id)

    async def is_owner_session_active(self, owner_id: UUID, session_id: UUID) -> bool:
        session = await self._sessions.is_active(owner_id, session_id, self._now())
        return session is not None and session.last_used_at + self._idle_ttl > self._now()

    async def logout(self, context: AuthenticatedOwnerContext) -> None:
        await self._sessions.revoke(context.owner.id, context.session.id, self._now())

    async def logout_all(self, context: AuthenticatedOwnerContext) -> None:
        await self._sessions.revoke_all(context.owner.id, self._now())

    async def list_sessions(self, context: AuthenticatedOwnerContext) -> list[OwnerSession]:
        return await self._sessions.list_for_owner(context.owner.id)

    async def revoke_session(self, context: AuthenticatedOwnerContext, session_id: UUID) -> bool:
        return await self._sessions.revoke(context.owner.id, session_id, self._now())
