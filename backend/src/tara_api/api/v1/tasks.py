"""Owner-scoped REST API transport for scheduled tasks (M16 Part B)."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from tara_api.api.v1.auth import authenticated_context
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.errors import ConflictError, ResourceNotFoundError, ValidationError
from tara_api.domain.tasks import ScheduleDefinition, ScheduledTaskCreateCommand, ScheduledTaskUpdateCommand
from tara_api.persistence.models import ScheduledTaskRunModel
from tara_api.tasks.service import ScheduledTask, ScheduledTaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


class ScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = "UTC"
    run_at: datetime
    interval_minutes: int | None = Field(default=None, ge=60, le=43200)
    occurrence_limit: int | None = Field(default=None, ge=1, le=365)

    @field_validator("run_at")
    @classmethod
    def utc_run_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("run_at_must_be_timezone_aware")
        return value.astimezone(UTC)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=1000)
    capability_id: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    schedule: ScheduleCreateRequest
    idempotency_key: str = Field(min_length=1, max_length=128)


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    instruction: str | None = Field(default=None, min_length=1, max_length=1000)
    capability_id: str | None = Field(default=None, min_length=1, max_length=100)
    target: str | None = Field(default=None, min_length=1, max_length=500)
    parameters: dict[str, Any] | None = None
    schedule: ScheduleCreateRequest | None = None


class ConfirmationApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str = Field(default="yes", min_length=1, max_length=50)


class ScheduledTaskResponse(BaseModel):
    id: UUID
    title: str
    kind: str
    schedule: dict[str, Any]
    state: str
    enabled: bool
    capability_id: str | None = None
    target_summary: str | None = None
    risk_level: str | None = None
    confirmation_id: UUID | None = None
    confirmation_status: str | None = None
    confirmation_expires_at: datetime | None = None
    confirmation_binding_hash: str | None = None

    @classmethod
    def from_domain(cls, task: ScheduledTask) -> "ScheduledTaskResponse":
        return cls(
            id=task.id,
            title=task.title,
            kind=task.kind.value if hasattr(task.kind, "value") else str(task.kind),
            schedule={
                "timezone": task.schedule.timezone,
                "run_at": task.schedule.run_at.astimezone(UTC).isoformat(),
                "interval_minutes": task.schedule.interval_minutes,
                "occurrence_limit": task.schedule.occurrence_limit,
            },
            state=task.state.value if hasattr(task.state, "value") else str(task.state),
            enabled=task.enabled,
            capability_id=task.capability_id,
            target_summary=task.target_summary,
            risk_level=task.risk_level,
            confirmation_id=task.confirmation_id,
            confirmation_status=task.confirmation_status,
            confirmation_expires_at=task.confirmation_expires_at,
            confirmation_binding_hash=task.confirmation_binding_hash,
        )


class TaskRunResponse(BaseModel):
    id: UUID
    run_id: UUID
    task_id: UUID
    scheduled_for: datetime
    claimed_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    state: str
    outcome_code: str | None = None
    error_code: str | None = None


@router.post("", response_model=ScheduledTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    request_data: TaskCreateRequest,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> ScheduledTaskResponse:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    schedule_def = ScheduleDefinition(
        timezone=request_data.schedule.timezone,
        run_at=request_data.schedule.run_at,
        interval_minutes=request_data.schedule.interval_minutes,
        occurrence_limit=request_data.schedule.occurrence_limit,
    )
    command = ScheduledTaskCreateCommand(
        title=request_data.title,
        instruction=request_data.instruction,
        capability_id=request_data.capability_id,
        target=request_data.target,
        parameters=request_data.parameters,
        schedule=schedule_def,
        idempotency_key=request_data.idempotency_key,
    )
    try:
        task = await service.create(context, command)
        return ScheduledTaskResponse.from_domain(task)
    except ValueError as error:
        error_msg = str(error)
        if error_msg == "idempotency_key_payload_mismatch":
            raise ConflictError("Idempotency key payload mismatch.") from error
        raise ValidationError({"task": error_msg}) from error


@router.get("", response_model=list[ScheduledTaskResponse])
async def list_tasks(
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> list[ScheduledTaskResponse]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    tasks = await service.list(context)
    return [ScheduledTaskResponse.from_domain(t) for t in tasks]


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> ScheduledTaskResponse:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    task = await service.get(context, task_id)
    if task is None:
        raise ResourceNotFoundError()
    return ScheduledTaskResponse.from_domain(task)


@router.put("/{task_id}", response_model=ScheduledTaskResponse)
async def update_task(
    task_id: UUID,
    request_data: TaskUpdateRequest,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> ScheduledTaskResponse:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    schedule_def: ScheduleDefinition | None = None
    if request_data.schedule is not None:
        schedule_def = ScheduleDefinition(
            timezone=request_data.schedule.timezone,
            run_at=request_data.schedule.run_at,
            interval_minutes=request_data.schedule.interval_minutes,
            occurrence_limit=request_data.schedule.occurrence_limit,
        )
    command = ScheduledTaskUpdateCommand(
        title=request_data.title,
        instruction=request_data.instruction,
        capability_id=request_data.capability_id,
        target=request_data.target,
        parameters=request_data.parameters,
        schedule=schedule_def,
    )
    try:
        updated = await service.update(context, task_id, command)
        if updated is None:
            raise ResourceNotFoundError()
        return ScheduledTaskResponse.from_domain(updated)
    except ValueError as error:
        raise ValidationError({"task": str(error)}) from error


@router.post("/{task_id}/pause", response_model=dict[str, bool])
async def pause_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, bool]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    if not await service.pause(context, task_id):
        raise ResourceNotFoundError()
    return {"success": True}


@router.post("/{task_id}/resume", response_model=dict[str, bool])
async def resume_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, bool]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    if not await service.resume(context, task_id):
        raise ResourceNotFoundError()
    return {"success": True}


@router.post("/{task_id}/enable", response_model=dict[str, bool])
async def enable_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, bool]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    if not await service.enable(context, task_id):
        raise ResourceNotFoundError()
    return {"success": True}


@router.post("/{task_id}/disable", response_model=dict[str, bool])
async def disable_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, bool]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    if not await service.disable(context, task_id):
        raise ResourceNotFoundError()
    return {"success": True}


@router.post("/{task_id}/cancel", response_model=dict[str, bool])
async def cancel_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, bool]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    if not await service.cancel(context, task_id):
        raise ResourceNotFoundError()
    return {"success": True}


@router.delete("/{task_id}", response_model=dict[str, bool])
async def delete_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, bool]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    if not await service.delete(context, task_id):
        raise ResourceNotFoundError()
    return {"success": True}


@router.post("/{task_id}/approve", response_model=ScheduledTaskResponse)
async def approve_confirmation(
    task_id: UUID,
    request_data: ConfirmationApprovalRequest,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> ScheduledTaskResponse:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    try:
        approved = await service.approve_confirmation(context, task_id, request_data.response)
        if approved is None:
            raise ResourceNotFoundError()
        return ScheduledTaskResponse.from_domain(approved)
    except ValueError as error:
        raise ValidationError({"confirmation": str(error)}) from error


@router.get("/{task_id}/runs", response_model=list[TaskRunResponse])
async def list_task_runs(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> list[TaskRunResponse]:
    service: ScheduledTaskService = request.app.state.scheduled_task_service
    task = await service.get(context, task_id)
    if task is None:
        raise ResourceNotFoundError()

    async with request.app.state.database.session() as session:
        runs = list(
            (
                await session.scalars(
                    select(ScheduledTaskRunModel)
                    .where(
                        ScheduledTaskRunModel.task_id == task_id,
                        ScheduledTaskRunModel.owner_id == context.owner.id,
                    )
                    .order_by(ScheduledTaskRunModel.claimed_at.desc())
                )
            ).all()
        )
    return [
        TaskRunResponse(
            id=run.id,
            run_id=run.run_id,
            task_id=run.task_id,
            scheduled_for=run.scheduled_for,
            claimed_at=run.claimed_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            state=run.state,
            outcome_code=run.outcome_code,
            error_code=run.error_code,
        )
        for run in runs
    ]
