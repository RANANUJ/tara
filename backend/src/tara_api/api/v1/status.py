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
    stt: dict[str, object]
    llm: dict[str, object]
    agent: dict[str, object]


@router.get("/status", response_model=StatusResponse)
async def service_status(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> StatusResponse:
    provider: ApplicationStatusProvider = request.app.state.status_provider
    snapshot = await provider.snapshot()
    stt = await request.app.state.stt_health.snapshot()
    llm = await request.app.state.llm_health.snapshot()
    queued, active, terminal = await request.app.state.agent_registry.counts()
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
        stt={
            "stt_configured": stt.configured, "stt_required": stt.required, "stt_provider": stt.provider, "stt_state": stt.state,
            "stt_ready": stt.ready, "stt_model_loaded": stt.model_loaded, "stt_language_mode": stt.language_mode,
            "stt_partial_mode": stt.partial_mode, "stt_queue_depth": stt.queue_depth, "stt_active_jobs": stt.active_jobs,
            "stt_max_queue": stt.max_queue, "stt_max_concurrency": stt.max_concurrency,
        },
        llm={
            "llm_configured": llm.configured,
            "llm_required": llm.required,
            "llm_provider": llm.provider,
            "llm_model": llm.model,
            "llm_state": llm.state.value,
            "llm_ready": llm.ready,
            "llm_streaming_supported": llm.streaming_supported,
            "llm_diagnostic_code": llm.diagnostic_code.value if llm.diagnostic_code else None,
        },
        agent={
            "agent_available": llm.ready,
            "agent_queue_depth": queued,
            "agent_active_requests": active,
            "agent_terminal_records": terminal,
        },
    )
