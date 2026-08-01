"""Minimal health endpoints for the backend bootstrap."""

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    """Response proving that the FastAPI process can serve requests."""

    status: Literal["ok"]


class DependencyStatus(BaseModel):
    """Typed readiness state for a bootstrap dependency."""

    name: str
    status: Literal["ready"]


class ReadinessResponse(BaseModel):
    """Response proving that bootstrap dependencies are ready."""

    status: Literal["ready"]
    dependencies: list[DependencyStatus]


@router.get("/health/live", response_model=LivenessResponse, status_code=status.HTTP_200_OK)
async def live() -> LivenessResponse:
    """Return process liveness without probing future product dependencies."""
    return LivenessResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def ready() -> ReadinessResponse:
    """Return typed bootstrap readiness without adding external dependencies."""
    return ReadinessResponse(
        status="ready",
        dependencies=[DependencyStatus(name="application", status="ready")],
    )
