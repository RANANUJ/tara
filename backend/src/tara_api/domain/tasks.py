"""Framework-neutral scheduled-task contracts for M16."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TaskKind(StrEnum):
    REMINDER = "reminder"
    BRIEFING = "briefing"


class TaskState(StrEnum):
    DRAFT = "draft"
    PENDING_CONFIRMATION = "pending_confirmation"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELED = "canceled"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ScheduleDefinition:
    """One-time or bounded hourly-or-slower recurrence in an IANA timezone."""

    timezone: str
    run_at: datetime
    interval_minutes: int | None = None
    occurrence_limit: int | None = None

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("invalid_timezone") from error
        if self.run_at.tzinfo is None:
            raise ValueError("run_at_must_be_timezone_aware")
        if self.interval_minutes is not None and not 60 <= self.interval_minutes <= 43_200:
            raise ValueError("invalid_recurrence_interval")
        if self.occurrence_limit is not None and not 1 <= self.occurrence_limit <= 365:
            raise ValueError("invalid_occurrence_limit")
        if self.interval_minutes is None and self.occurrence_limit is not None:
            raise ValueError("one_time_schedule_cannot_have_occurrence_limit")

    def next_after(self, now: datetime) -> datetime | None:
        if now.tzinfo is None:
            raise ValueError("now_must_be_timezone_aware")
        current = self.run_at.astimezone(UTC)
        if self.interval_minutes is None:
            return current if current > now.astimezone(UTC) else None
        interval = timedelta(minutes=self.interval_minutes)
        while current <= now.astimezone(UTC):
            current += interval
        return current


@dataclass(frozen=True, slots=True)
class ScheduledTaskCreateCommand:
    title: str
    instruction: str
    capability_id: str
    target: str
    parameters: dict[str, str | int | bool | None]
    schedule: ScheduleDefinition
    idempotency_key: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.title.strip()) <= 160 or not 1 <= len(self.instruction.strip()) <= 1024:
            raise ValueError("invalid_task_input")
        if not self.capability_id.replace(".", "").replace("_", "").isalnum() or len(self.capability_id) > 128:
            raise ValueError("invalid_capability_id")
        if not self.target.strip() or len(self.target) > 256 or len(self.parameters) > 32 or not self.idempotency_key:
            raise ValueError("invalid_task_input")

    def binding_hash(self) -> str:
        payload = {
            "capability": self.capability_id,
            "target": self.target.strip(),
            "parameters": self.parameters,
            "instruction": self.instruction.strip(),
            "run_at": self.schedule.run_at.astimezone(UTC).isoformat(),
            "timezone": self.schedule.timezone,
            "interval": self.schedule.interval_minutes,
            "count": self.schedule.occurrence_limit,
        }
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid_task_parameters") from error
        return sha256(encoded.encode()).hexdigest()
