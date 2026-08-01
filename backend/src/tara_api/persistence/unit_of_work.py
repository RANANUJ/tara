"""Explicit async transaction boundaries for persistence operations."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tara_api.persistence.repositories.sqlalchemy import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfirmationRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationTurnRepository,
    SqlAlchemyPermissionSettingRepository,
    SqlAlchemySafeServiceConfigurationRepository,
    SqlAlchemySchedulerJobMetadataRepository,
    SqlAlchemyStructuredMemoryRepository,
)


class SqlAlchemyUnitOfWork:
    """Commit on successful scope exit and roll back any failed persistence scope."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        await self._session.begin()
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exception_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    @property
    def conversations(self) -> SqlAlchemyConversationRepository:
        return SqlAlchemyConversationRepository(self._require_session())

    @property
    def turns(self) -> SqlAlchemyConversationTurnRepository:
        return SqlAlchemyConversationTurnRepository(self._require_session())

    @property
    def memories(self) -> SqlAlchemyStructuredMemoryRepository:
        return SqlAlchemyStructuredMemoryRepository(self._require_session())

    @property
    def permissions(self) -> SqlAlchemyPermissionSettingRepository:
        return SqlAlchemyPermissionSettingRepository(self._require_session())

    @property
    def confirmations(self) -> SqlAlchemyConfirmationRepository:
        return SqlAlchemyConfirmationRepository(self._require_session())

    @property
    def audit_events(self) -> SqlAlchemyAuditEventRepository:
        return SqlAlchemyAuditEventRepository(self._require_session())

    @property
    def scheduler_jobs(self) -> SqlAlchemySchedulerJobMetadataRepository:
        return SqlAlchemySchedulerJobMetadataRepository(self._require_session())

    @property
    def service_configurations(self) -> SqlAlchemySafeServiceConfigurationRepository:
        return SqlAlchemySafeServiceConfigurationRepository(self._require_session())

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work must be used inside an async context manager")
        return self._session
