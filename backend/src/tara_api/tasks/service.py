"""Owner-scoped M16 task CRUD with explicit database transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select

from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.tasks import ScheduleDefinition, TaskKind, TaskState
from tara_api.persistence.database import Database
from tara_api.persistence.models import ScheduledTaskModel


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    id: UUID
    title: str
    kind: TaskKind
    schedule: ScheduleDefinition
    state: TaskState
    enabled: bool


class ScheduledTaskService:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, context: AuthenticatedOwnerContext, *, title: str, kind: TaskKind, instruction: str, schedule: ScheduleDefinition, idempotency_key: str) -> ScheduledTask:
        title, instruction = title.strip(), instruction.strip()
        if not title or len(title) > 160 or not instruction or len(instruction) > 1024 or not idempotency_key:
            raise ValueError("invalid_task_input")
        key_hash = sha256(idempotency_key.encode()).hexdigest()
        async with self._database.unit_of_work() as unit:
            session = unit._require_session()  # noqa: SLF001
            existing = await session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == context.owner.id, ScheduledTaskModel.idempotency_key_hash == key_hash))
            if existing is not None:
                return self._record(existing)
            model = ScheduledTaskModel(
                owner_id=context.owner.id, owner_session_id=context.session.id, title=title, task_kind=kind.value,
                instruction=instruction, schedule={"run_at": schedule.run_at.astimezone(UTC).isoformat(), "interval_minutes": schedule.interval_minutes, "occurrence_limit": schedule.occurrence_limit}, timezone=schedule.timezone,
                enabled=True, state=TaskState.ACTIVE.value, next_run_at=schedule.next_after(datetime.now(UTC)), idempotency_key_hash=key_hash,
            )
            session.add(model)
            await session.flush()
            return self._record(model)

    async def list(self, context: AuthenticatedOwnerContext) -> list[ScheduledTask]:
        async with self._database.unit_of_work() as unit:
            session = unit._require_session()  # noqa: SLF001
            rows = (await session.scalars(select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == context.owner.id).order_by(ScheduledTaskModel.created_at))).all()
            return [self._record(row) for row in rows]

    async def pause(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        async with self._database.unit_of_work() as unit:
            session = unit._require_session()  # noqa: SLF001
            row = await session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.owner_id == context.owner.id))
            if row is None:
                return False
            row.state, row.enabled, row.next_run_at = TaskState.PAUSED.value, False, None
            return True

    @staticmethod
    def _record(row: ScheduledTaskModel) -> ScheduledTask:
        schedule = ScheduleDefinition(row.timezone, datetime.fromisoformat(str(row.schedule["run_at"])), row.schedule.get("interval_minutes"), row.schedule.get("occurrence_limit"))
        return ScheduledTask(row.id, row.title, TaskKind(row.task_kind), schedule, TaskState(row.state), row.enabled)
