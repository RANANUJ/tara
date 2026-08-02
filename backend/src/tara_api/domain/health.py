"""Framework-independent health and operational-status contracts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DependencyName(StrEnum):
    APPLICATION = "application"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    SCHEMA = "schema"
    STT = "stt"
    LLM = "llm"
    TTS = "tts"
    WAKEWORD = "wakeword"


class HealthSeverity(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: DependencyName
    state: HealthState
    severity: HealthSeverity
    checked_at: datetime
    latency_ms: int
    diagnostic: str | None = None
    last_success_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() != UTC.utcoffset(self.checked_at):
            raise ValueError("checked_at must be UTC")
        if self.last_success_at and (self.last_success_at.tzinfo is None or self.last_success_at.utcoffset() != UTC.utcoffset(self.last_success_at)):
            raise ValueError("last_success_at must be UTC")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")


@dataclass(frozen=True, slots=True)
class ServiceReadiness:
    state: HealthState
    ready: bool
    dependencies: tuple[HealthCheckResult, ...]


@dataclass(frozen=True, slots=True)
class ServiceStatusSnapshot:
    application_name: str
    version: str
    environment: str
    uptime_ms: int
    state: HealthState
    dependencies: tuple[HealthCheckResult, ...]
    features: dict[str, bool]
    build_revision: str | None = None

    def __post_init__(self) -> None:
        if self.uptime_ms < 0:
            raise ValueError("uptime_ms cannot be negative")
