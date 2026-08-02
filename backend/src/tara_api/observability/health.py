"""Bounded, safe dependency health checks for implemented Tara services only."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tara_api.domain.errors import OperationTimeoutError
from tara_api.domain.health import DependencyName, HealthCheckResult, HealthSeverity, HealthState, ServiceReadiness
from tara_api.observability.timeout import run_with_timeout
from tara_api.persistence.database import Database


class Clock(Protocol):
    def now(self) -> datetime: ...


class HealthCheck(Protocol):
    name: DependencyName
    severity: HealthSeverity

    async def check(self) -> tuple[HealthState, str | None]: ...


class HealthRegistry(Protocol):
    async def readiness(self) -> ServiceReadiness: ...

    async def checks(self) -> tuple[HealthCheckResult, ...]: ...


class StatusProvider(Protocol):
    async def readiness(self) -> ServiceReadiness: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class CallableHealthCheck:
    def __init__(
        self,
        name: DependencyName,
        severity: HealthSeverity,
        operation: Callable[[], Awaitable[tuple[HealthState, str | None]]],
    ) -> None:
        self.name = name
        self.severity = severity
        self._operation = operation

    async def check(self) -> tuple[HealthState, str | None]:
        return await self._operation()


class DependencyHealthRegistry:
    def __init__(self, checks: tuple[HealthCheck, ...], clock: Clock, timeout_seconds: float, concurrency_limit: int = 4) -> None:
        if timeout_seconds <= 0 or concurrency_limit <= 0:
            raise ValueError("health timeouts and concurrency limits must be positive")
        self._registered_checks = checks
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self._last_success: dict[DependencyName, datetime] = {}

    async def checks(self) -> tuple[HealthCheckResult, ...]:
        return tuple(await asyncio.gather(*(self._run_check(check) for check in self._registered_checks)))

    async def readiness(self) -> ServiceReadiness:
        results = await self.checks()
        unavailable_required = any(result.severity == HealthSeverity.REQUIRED and result.state == HealthState.UNAVAILABLE for result in results)
        degraded = any(result.state in {HealthState.DEGRADED, HealthState.UNKNOWN} for result in results)
        state = HealthState.UNAVAILABLE if unavailable_required else HealthState.DEGRADED if degraded else HealthState.HEALTHY
        return ServiceReadiness(state=state, ready=not unavailable_required, dependencies=results)

    async def _run_check(self, check: HealthCheck) -> HealthCheckResult:
        started = time.monotonic()
        checked_at = self._clock.now()
        try:
            async with self._semaphore:
                state, diagnostic = await run_with_timeout(check.check(), self._timeout_seconds)
        except OperationTimeoutError:
            state, diagnostic = HealthState.UNAVAILABLE, "Health check timed out."
        except Exception:
            state, diagnostic = HealthState.UNAVAILABLE, "Health check failed."
        latency_ms = max(0, round((time.monotonic() - started) * 1000))
        if state == HealthState.HEALTHY:
            self._last_success[check.name] = checked_at
        return HealthCheckResult(check.name, state, check.severity, checked_at, latency_ms, diagnostic, self._last_success.get(check.name))


def implemented_health_checks(database: Database, stt_check: HealthCheck | None = None) -> tuple[HealthCheck, ...]:
    async def application() -> tuple[HealthState, str | None]:
        return HealthState.HEALTHY, None

    async def database_check() -> tuple[HealthState, str | None]:
        return (HealthState.HEALTHY, None) if (await database.check_connection()).available else (HealthState.UNAVAILABLE, "Database is unavailable.")

    async def authentication() -> tuple[HealthState, str | None]:
        try:
            async with database.engine.connect() as connection:
                await connection.execute(text("SELECT 1 FROM owners LIMIT 1"))
        except (OSError, SQLAlchemyError):
            return HealthState.UNAVAILABLE, "Authentication storage is unavailable."
        return HealthState.HEALTHY, None

    async def schema() -> tuple[HealthState, str | None]:
        try:
            async with database.engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        except (OSError, SQLAlchemyError):
            return HealthState.UNAVAILABLE, "Schema status is unavailable."
        return (HealthState.HEALTHY, None) if revision == "20260801_0004" else (HealthState.DEGRADED, "Schema revision is not current.")

    checks: tuple[HealthCheck, ...] = (
        CallableHealthCheck(DependencyName.APPLICATION, HealthSeverity.REQUIRED, application),
        CallableHealthCheck(DependencyName.DATABASE, HealthSeverity.REQUIRED, database_check),
        CallableHealthCheck(DependencyName.AUTHENTICATION, HealthSeverity.REQUIRED, authentication),
        CallableHealthCheck(DependencyName.SCHEMA, HealthSeverity.OPTIONAL, schema),
    )
    return checks + ((stt_check,) if stt_check else ())
