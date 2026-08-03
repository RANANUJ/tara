"""Owner-scoped M16 task CRUD with explicit database transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select

from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.models import JsonValue, ToolRequest
from tara_api.domain.protocols import (
    ActionPolicyService,
    AuthenticatedConfirmationService,
    ToolRegistry,
)
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, TaskKind, TaskState
from tara_api.persistence.database import Database
from tara_api.persistence.models import ScheduledTaskModel
from tara_api.tasks.mapping import CapabilityTaskMapper, MappedTaskCapability


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    id: UUID
    title: str
    kind: TaskKind
    schedule: ScheduleDefinition
    state: TaskState
    enabled: bool
    capability_id: str | None = None
    target_summary: str | None = None
    target_identity_hash: str | None = None
    parameters_hash: str | None = None
    risk_level: str | None = None
    confirmation_id: UUID | None = None
    confirmation_status: str | None = None
    confirmation_expires_at: datetime | None = None
    confirmation_binding_hash: str | None = None


class ScheduledTaskService:
    def __init__(
        self,
        database: Database,
        capability_registry: ToolRegistry,
        policy: ActionPolicyService,
        confirmations: AuthenticatedConfirmationService,
    ) -> None:
        self._database = database
        self._capability_registry = capability_registry
        self._policy = policy
        self._confirmations = confirmations

    async def create(self, context: AuthenticatedOwnerContext, command: ScheduledTaskCreateCommand) -> ScheduledTask:
        mapped = CapabilityTaskMapper(self._capability_registry, self._policy).map(command)
        key_hash = sha256(command.idempotency_key.encode()).hexdigest()
        payload_hash = command.binding_hash()
        async with self._database.unit_of_work() as unit:
            session = unit._require_session()  # noqa: SLF001
            existing = await session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.owner_id == context.owner.id, ScheduledTaskModel.idempotency_key_hash == key_hash))
            if existing is not None:
                if existing.schedule.get("idempotency_payload_hash") != payload_hash:
                    raise ValueError("idempotency_key_payload_mismatch")
                if mapped.confirmation_required and existing.confirmation_id is None:
                    raise ValueError("task_confirmation_unavailable")
                return self._record(existing)
            model = ScheduledTaskModel(
                owner_id=context.owner.id,
                owner_session_id=context.session.id,
                title=command.title.strip(),
                task_kind=TaskKind.REMINDER.value,
                instruction=command.instruction.strip(),
                schedule={
                    "run_at": command.schedule.run_at.astimezone(UTC).isoformat(),
                    "interval_minutes": command.schedule.interval_minutes,
                    "occurrence_limit": command.schedule.occurrence_limit,
                    "idempotency_payload_hash": payload_hash,
                },
                timezone=command.schedule.timezone,
                capability_id=mapped.capability_id,
                target_summary=mapped.target_summary,
                target_identity_hash=mapped.target_hash,
                parameters_hash=mapped.parameters_hash,
                confirmation_binding_hash=mapped.binding_hash,
                risk_level=mapped.risk_level,
                enabled=not mapped.confirmation_required,
                state=(
                    TaskState.PENDING_CONFIRMATION if mapped.confirmation_required else TaskState.ACTIVE
                ).value,
                next_run_at=(
                    None
                    if mapped.confirmation_required
                    else command.schedule.next_after(datetime.now(UTC))
                ),
                idempotency_key_hash=key_hash,
            )
            await unit.scheduled_tasks.add(model)

        if not mapped.confirmation_required:
            return self._record(model)

        request = self._confirmation_request(model.id, command, mapped)
        try:
            confirmation = await self._confirmations.create_authenticated(
                context,
                request,
                mapped.definition,
            )
        except Exception as error:
            raise ValueError("task_confirmation_unavailable") from error
        if confirmation is None:
            raise ValueError("task_confirmation_unavailable")

        async with self._database.unit_of_work() as unit:
            attached = await unit.scheduled_tasks.attach_confirmation(
                model.id,
                context.owner.id,
                confirmation.id,
                confirmation.status.value,
                mapped.binding_hash,
                confirmation.expires_at,
            )
        if attached is None:
            raise ValueError("task_confirmation_unavailable")
        return self._record(attached)

    async def mark_pending_confirmation(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        """M14 approval is required before a consequential task may be scheduled."""
        async with self._database.unit_of_work() as unit:
            row = await unit.scheduled_tasks.get_for_owner(task_id, context.owner.id)
            if row is None or row.state in {TaskState.CANCELED.value, TaskState.COMPLETED.value, TaskState.FAILED.value}:
                return False
            row.state = TaskState.PENDING_CONFIRMATION.value
            row.enabled = False
            row.next_run_at = None
            return True

    async def list(self, context: AuthenticatedOwnerContext) -> list[ScheduledTask]:
        async with self._database.unit_of_work() as unit:
            rows = await unit.scheduled_tasks.list_for_owner(context.owner.id)
            return [self._record(row) for row in rows]

    async def pause(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        async with self._database.unit_of_work() as unit:
            row = await unit.scheduled_tasks.get_for_owner(task_id, context.owner.id)
            if row is None:
                return False
            row.state, row.enabled, row.next_run_at = TaskState.PAUSED.value, False, None
            return True

    async def get(self, context: AuthenticatedOwnerContext, task_id: UUID) -> ScheduledTask | None:
        async with self._database.unit_of_work() as unit:
            row = await unit.scheduled_tasks.get_for_owner(task_id, context.owner.id)
            return self._record(row) if row else None

    async def update(self, context: AuthenticatedOwnerContext, task_id: UUID, values: dict[str, object]) -> ScheduledTask | None:
        allowed = {"title", "instruction", "schedule"}
        if not values or set(values) - allowed:
            raise ValueError("invalid_task_update")
        async with self._database.unit_of_work() as unit:
            row = await unit.scheduled_tasks.get_for_owner(task_id, context.owner.id)
            if row is None:
                return None
            if row.state in {TaskState.CANCELED.value, TaskState.COMPLETED.value, TaskState.FAILED.value}:
                raise ValueError("task_not_mutable")
            if "title" in values:
                title = values["title"]
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
                    raise ValueError("invalid_task_update")
                row.title = title.strip()
            if "instruction" in values:
                instruction = values["instruction"]
                if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 1024:
                    raise ValueError("invalid_task_update")
                row.instruction = instruction.strip()
            if "schedule" in values:
                schedule = values["schedule"]
                if not isinstance(schedule, ScheduleDefinition):
                    raise ValueError("invalid_task_update")
                row.schedule = {"run_at": schedule.run_at.astimezone(UTC).isoformat(), "interval_minutes": schedule.interval_minutes, "occurrence_limit": schedule.occurrence_limit}
                row.timezone = schedule.timezone
                row.next_run_at = schedule.next_after(datetime.now(UTC)) if row.enabled else None
            return self._record(row)

    async def resume(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        return await self._set_state(context, task_id, TaskState.ACTIVE, True)

    async def disable(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        return await self._set_state(context, task_id, TaskState.DISABLED, False)

    async def enable(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        return await self._set_state(context, task_id, TaskState.ACTIVE, True)

    async def cancel(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        return await self._set_state(context, task_id, TaskState.CANCELED, False, idempotent=True)

    async def delete(self, context: AuthenticatedOwnerContext, task_id: UUID) -> bool:
        async with self._database.unit_of_work() as unit:
            return await unit.scheduled_tasks.delete_for_owner(task_id, context.owner.id)

    async def _set_state(self, context: AuthenticatedOwnerContext, task_id: UUID, state: TaskState, enabled: bool, *, idempotent: bool = False) -> bool:
        async with self._database.unit_of_work() as unit:
            session = unit._require_session()  # noqa: SLF001
            row = await session.scalar(select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id, ScheduledTaskModel.owner_id == context.owner.id))
            if row is None:
                return False
            if row.state == TaskState.CANCELED.value:
                return idempotent and state is TaskState.CANCELED
            row.state, row.enabled = state.value, enabled
            row.next_run_at = self._record(row).schedule.next_after(datetime.now(UTC)) if enabled else None
            return True

    @staticmethod
    def _record(row: ScheduledTaskModel) -> ScheduledTask:
        schedule = ScheduleDefinition(row.timezone, datetime.fromisoformat(str(row.schedule["run_at"])), row.schedule.get("interval_minutes"), row.schedule.get("occurrence_limit"))
        return ScheduledTask(
            id=row.id,
            title=row.title,
            kind=TaskKind(row.task_kind),
            schedule=schedule,
            state=TaskState(row.state),
            enabled=row.enabled,
            capability_id=row.capability_id,
            target_summary=row.target_summary,
            target_identity_hash=row.target_identity_hash,
            parameters_hash=row.parameters_hash,
            risk_level=row.risk_level,
            confirmation_id=row.confirmation_id,
            confirmation_status=row.confirmation_status,
            confirmation_expires_at=row.confirmation_expires_at,
            confirmation_binding_hash=row.confirmation_binding_hash,
        )

    @staticmethod
    def _confirmation_request(
        task_id: UUID,
        command: ScheduledTaskCreateCommand,
        mapped: MappedTaskCapability,
    ) -> ToolRequest:
        schedule: dict[str, JsonValue] = {
            "run_at": command.schedule.run_at.astimezone(UTC).isoformat(),
            "interval_minutes": command.schedule.interval_minutes,
            "occurrence_limit": command.schedule.occurrence_limit,
        }
        binding: dict[str, JsonValue] = {
            "task_id": str(task_id),
            "capability_id": mapped.capability_id,
            "target_identity_hash": mapped.target_hash,
            "parameters_hash": mapped.parameters_hash,
            "instruction_hash": sha256(command.instruction.strip().encode()).hexdigest(),
            "schedule": schedule,
            "timezone": command.schedule.timezone,
            "task_binding_hash": mapped.binding_hash,
        }
        return ToolRequest(mapped.definition.name, mapped.definition.version, binding)
