"""Safe process liveness and dependency readiness endpoints."""

from typing import Literal, cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tara_api.domain.health import HealthCheckResult, ServiceReadiness
from tara_api.observability.health import HealthRegistry

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class DependencyStatus(BaseModel):
    name: str
    state: str
    required: bool
    checked_at: str
    latency_ms: int
    diagnostic: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    ready: bool
    dependencies: list[DependencyStatus]


def _dependency(result: HealthCheckResult) -> DependencyStatus:
    return DependencyStatus(
        name=result.name.value,
        state=result.state.value,
        required=result.severity.value == "required",
        checked_at=result.checked_at.isoformat(),
        latency_ms=result.latency_ms,
        diagnostic=result.diagnostic,
    )


def _response(result: ServiceReadiness) -> ReadinessResponse:
    return ReadinessResponse(status=result.state.value, ready=result.ready, dependencies=[_dependency(item) for item in result.dependencies])


@router.get("/health/live", response_model=LivenessResponse, status_code=status.HTTP_200_OK)
async def live() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse, responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}})
async def ready(request: Request) -> ReadinessResponse | JSONResponse:
    registry = cast(HealthRegistry, request.app.state.health_registry)
    result = await registry.readiness()
    response = _response(result)
    if not result.ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response.model_dump())
    return response
