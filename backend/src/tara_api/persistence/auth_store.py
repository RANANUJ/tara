"""SQLAlchemy authentication adapter returning only domain records."""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult

from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerCredential, OwnerSession
from tara_api.persistence.database import Database
from tara_api.persistence.models import AuditEventModel, OwnerModel, OwnerSessionModel


class SqlAlchemyAuthenticationStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def bootstrap_required(self) -> bool:
        async with self._database.session() as session:
            return (await session.scalar(select(OwnerModel.id).limit(1))) is None

    async def bootstrap(self, email: str, password_hash: str) -> Owner | None:
        try:
            async with self._database.session() as session, session.begin():
                model = OwnerModel(normalized_email=email, password_hash=password_hash, owner_slot=1)
                session.add(model)
                await session.flush()
                return self._owner(model)
        except Exception:
            return None

    async def get_by_email(self, email: str) -> OwnerCredential | None:
        async with self._database.session() as session:
            model = await session.scalar(select(OwnerModel).where(OwnerModel.normalized_email == email))
        return OwnerCredential(self._owner(model), model.password_hash) if model else None

    async def record_login_audit(self, outcome: str, occurred_at: datetime) -> None:
        async with self._database.session() as session, session.begin():
            session.add(AuditEventModel(event_type="authentication.login", outcome=outcome, occurred_at=occurred_at))

    async def create(self, owner_id: UUID, token_hash: str, expires_at: datetime, client_label: str | None) -> OwnerSession:
        async with self._database.session() as session, session.begin():
            now = datetime.now(expires_at.tzinfo)
            model = OwnerSessionModel(owner_id=owner_id, token_hash=token_hash, issued_at=now, expires_at=expires_at, last_used_at=now, client_label=client_label)
            session.add(model)
            await session.flush()
            return self._session(model)

    async def authenticate(self, token_hash: str, now: datetime) -> AuthenticatedOwnerContext | None:
        async with self._database.session() as session, session.begin():
            row = await session.execute(select(OwnerSessionModel, OwnerModel).join(OwnerModel).where(OwnerSessionModel.token_hash == token_hash))
            pair = row.one_or_none()
            if pair is None:
                return None
            session_model, owner_model = pair
            if session_model.revoked_at is not None or session_model.expires_at <= now:
                return None
            if now - session_model.last_used_at >= __import__("datetime").timedelta(minutes=5):
                session_model.last_used_at = now
            return AuthenticatedOwnerContext(self._owner(owner_model), self._session(session_model))

    async def revoke(self, owner_id: UUID, session_id: UUID, now: datetime) -> bool:
        async with self._database.session() as session, session.begin():
            result = await session.execute(update(OwnerSessionModel).where(OwnerSessionModel.id == session_id, OwnerSessionModel.owner_id == owner_id, OwnerSessionModel.revoked_at.is_(None)).values(revoked_at=now))
            return bool(cast(CursorResult[object], result).rowcount)

    async def revoke_all(self, owner_id: UUID, now: datetime) -> None:
        async with self._database.session() as session, session.begin():
            await session.execute(update(OwnerSessionModel).where(OwnerSessionModel.owner_id == owner_id, OwnerSessionModel.revoked_at.is_(None)).values(revoked_at=now))

    async def list_for_owner(self, owner_id: UUID) -> list[OwnerSession]:
        async with self._database.session() as session:
            models = await session.scalars(select(OwnerSessionModel).where(OwnerSessionModel.owner_id == owner_id).order_by(OwnerSessionModel.issued_at.desc()))
            return [self._session(model) for model in models]

    @staticmethod
    def _owner(model: OwnerModel) -> Owner:
        return Owner(model.id, model.normalized_email, model.created_at)

    @staticmethod
    def _session(model: OwnerSessionModel) -> OwnerSession:
        return OwnerSession(model.id, model.owner_id, model.issued_at, model.expires_at, model.last_used_at, model.revoked_at, model.client_label)
