"""SQLAlchemy declarative base and UTC timestamp storage type."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from tara_api.persistence.types import ensure_utc


class Base(DeclarativeBase):
    """Base class for ORM entities that remain internal to persistence."""


class UTCDateTime(TypeDecorator[datetime]):
    """Store timestamps as UTC and restore SQLite values as aware UTC datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect: Dialect) -> datetime | None:
        """Normalize every persisted timestamp to UTC."""
        if value is None:
            return None
        return ensure_utc(value)

    def process_result_value(self, value: datetime | None, _dialect: Dialect) -> datetime | None:
        """Restore SQLite's timezone-naive values as UTC-aware timestamps."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
