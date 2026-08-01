"""Clock implementations used by deterministic safety services."""

from datetime import UTC, datetime


class SystemClock:
    """Provide timezone-aware UTC time outside persistence and framework code."""

    def now(self) -> datetime:
        return datetime.now(UTC)
