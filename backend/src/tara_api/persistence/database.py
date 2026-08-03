"""Async SQLAlchemy engine, session factory, and SQLite lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from tara_api.persistence.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Safe database readiness result for health reporting."""

    available: bool


class Database:
    """Own the async engine and make SQLite connection rules explicit."""

    def __init__(self, database_url: str, encryption_key: str | None = None) -> None:
        self.database_url = database_url
        self.encryption_key = encryption_key
        connect_args: dict[str, object] = {}
        if self._is_sqlite:
            connect_args["timeout"] = 30

        self.engine: AsyncEngine = create_async_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        if self._is_sqlite:
            event.listen(self.engine.sync_engine, "connect", self._enable_sqlite_foreign_keys)
            if self.encryption_key:
                event.listen(self.engine.sync_engine, "connect", self._set_sqlite_encryption_key)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @property
    def _is_sqlite(self) -> bool:
        return make_url(self.database_url).drivername.startswith("sqlite")

    async def start(self) -> None:
        """Prepare local SQLite parent directories without creating schema automatically."""
        if not self._is_sqlite:
            return

        database_name = make_url(self.database_url).database
        if database_name and database_name != ":memory:" and not database_name.startswith("file:"):
            Path(database_name).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    async def dispose(self) -> None:
        """Release engine resources during application shutdown."""
        await self.engine.dispose()

    async def check_connection(self) -> DatabaseHealth:
        """Check database reachability without exposing connection details."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except (OSError, SQLAlchemyError):
            return DatabaseHealth(available=False)
        return DatabaseHealth(available=True)

    async def check_integrity(self) -> bool:
        """Verify database integrity via PRAGMA integrity_check."""
        try:
            async with self.engine.connect() as connection:
                res = await connection.execute(text("PRAGMA integrity_check"))
                row = res.fetchone()
                return bool(row and row[0] == "ok")
        except (OSError, SQLAlchemyError):
            return False

    def session(self) -> AsyncSession:
        """Create a session for a unit-of-work transaction boundary."""
        return self.session_factory()

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """Create an explicit transaction boundary for repository operations."""
        from tara_api.persistence.unit_of_work import SqlAlchemyUnitOfWork

        return SqlAlchemyUnitOfWork(self.session_factory)

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
        """Enable SQLite foreign-key enforcement for every new connection."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    def _set_sqlite_encryption_key(self, dbapi_connection: Any, _connection_record: Any) -> None:
        """Apply PRAGMA key for SQLCipher/encrypted SQLite connections."""
        if not self.encryption_key:
            return
        cursor = dbapi_connection.cursor()
        try:
            escaped_key = self.encryption_key.replace("'", "''")
            cursor.execute(f"PRAGMA key = '{escaped_key}'")
        finally:
            cursor.close()
