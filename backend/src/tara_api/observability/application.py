"""Safe application metadata and status snapshots."""

import time
from datetime import datetime

from tara_api.domain.health import ServiceStatusSnapshot
from tara_api.observability.health import HealthRegistry


class ApplicationStatusProvider:
    def __init__(
        self,
        registry: HealthRegistry,
        app_name: str,
        version: str,
        environment: str,
        started_at: datetime,
        build_revision: str | None,
    ) -> None:
        self._registry = registry
        self._app_name = app_name
        self._version = version
        self._environment = environment
        self._started_at = started_at
        self._started_monotonic = time.monotonic()
        self._build_revision = build_revision

    async def snapshot(self) -> ServiceStatusSnapshot:
        readiness = await self._registry.readiness()
        return ServiceStatusSnapshot(
            self._app_name,
            self._version,
            self._environment,
            max(0, round((time.monotonic() - self._started_monotonic) * 1000)),
            readiness.state,
            readiness.dependencies,
            {"database_persistence": True, "owner_authentication": True, "session_management": True},
            self._build_revision,
        )
