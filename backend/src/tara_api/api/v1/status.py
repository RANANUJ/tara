"""Authenticated safe operational status for implemented backend features."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from tara_api.api.v1.auth import authenticated_context
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.observability.application import ApplicationStatusProvider

router = APIRouter(tags=["status"])


class StatusDependency(BaseModel):
    name: str
    state: str
    required: bool
    checked_at: str
    latency_ms: int
    diagnostic: str | None = None
    last_success_at: str | None = None


class StatusResponse(BaseModel):
    application_name: str
    version: str
    environment: str
    build_revision: str | None
    uptime_ms: int
    state: str
    dependencies: list[StatusDependency]
    features: dict[str, bool]


@router.get("/status", response_model=StatusResponse)
async def service_status(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> StatusResponse:
    provider: ApplicationStatusProvider = request.app.state.status_provider
    snapshot = await provider.snapshot()
    return StatusResponse(
        application_name=snapshot.application_name,
        version=snapshot.version,
        environment=snapshot.environment,
        build_revision=snapshot.build_revision,
        uptime_ms=snapshot.uptime_ms,
        state=snapshot.state.value,
        dependencies=[
            StatusDependency(
                name=item.name.value,
                state=item.state.value,
                required=item.severity.value == "required",
                checked_at=item.checked_at.isoformat(),
                latency_ms=item.latency_ms,
                diagnostic=item.diagnostic,
                last_success_at=item.last_success_at.isoformat() if item.last_success_at else None,
            )
            for item in snapshot.dependencies
        ],
        features=snapshot.features,
    )
