"""Minimal health endpoints for the backend bootstrap."""

from typing import Literal, cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tara_api.persistence.database import Database

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    """Response proving that the FastAPI process can serve requests."""

    status: Literal["ok"]


class DependencyStatus(BaseModel):
    """Typed readiness state for a bootstrap dependency."""

    name: str
    status: Literal["ready", "unavailable"]


class ReadinessResponse(BaseModel):
    """Response proving that bootstrap dependencies are ready."""

    status: Literal["ready", "unavailable"]
    dependencies: list[DependencyStatus]


@router.get("/health/live", response_model=LivenessResponse, status_code=status.HTTP_200_OK)
async def live() -> LivenessResponse:
    """Return process liveness without probing future product dependencies."""
    return LivenessResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(request: Request) -> ReadinessResponse | JSONResponse:
    """Return readiness that reports the local persistence dependency honestly."""
    database = cast(Database, request.app.state.database)
    database_health = await database.check_connection()
    dependency_status: Literal["ready", "unavailable"] = (
        "ready" if database_health.available else "unavailable"
    )
    response = ReadinessResponse(
        status="ready" if database_health.available else "unavailable",
        dependencies=[
            DependencyStatus(name="application", status="ready"),
            DependencyStatus(name="database", status=dependency_status),
        ],
    )
    if not database_health.available:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response.model_dump())
    return response
