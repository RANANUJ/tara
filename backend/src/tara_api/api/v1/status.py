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
    tts: dict[str, object]
    wakeword: dict[str, object]
    tasks: dict[str, object]


@router.get("/status", response_model=StatusResponse)
async def service_status(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> StatusResponse:
    provider: ApplicationStatusProvider = request.app.state.status_provider
    snapshot = await provider.snapshot()
    stt = await request.app.state.stt_health.snapshot()
    llm = await request.app.state.llm_health.snapshot()
    tts = await request.app.state.tts_health.snapshot()
    wakeword = await request.app.state.wakeword_health.snapshot()
    wakeword_active_connections = await request.app.state.wakeword_service.active_connections()
    queued, active, terminal = await request.app.state.agent_registry.counts()
    tts_queued, tts_active, _tts_terminal, retained_audio = await request.app.state.tts_registry.counts()
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
        tts={
            "tts_configured": tts.configured,
            "tts_required": tts.required,
            "tts_provider": tts.provider,
            "tts_state": tts.state.value,
            "tts_ready": tts.ready,
            "tts_voice": tts.voice,
            "tts_language_mode": tts.language_mode,
            "tts_format": {
                "encoding": tts.output_format.encoding.value,
                "sample_rate": tts.output_format.sample_rate,
                "channels": tts.output_format.channels,
                "bit_depth": tts.output_format.bit_depth,
            }
            if tts.output_format
            else None,
            "tts_streaming_mode": "post_synthesis_chunks",
            "tts_queue_depth": tts_queued,
            "tts_active_requests": tts_active,
            "tts_retained_audio_bytes": retained_audio,
            "tts_max_queue": request.app.state.settings.tts_max_queued_requests,
            "tts_max_concurrency": request.app.state.settings.tts_max_concurrent_requests,
        },
        wakeword={
            "wakeword_configured": wakeword.configured,
            "wakeword_enabled": wakeword.enabled,
            "wakeword_required": request.app.state.settings.wakeword_required,
            "wakeword_provider": wakeword.provider,
            "wakeword_state": wakeword.state.value,
            "wakeword_ready": wakeword.ready,
            "wakeword_phrase_configured": wakeword.phrase_configured,
            "wakeword_foreground_only": wakeword.foreground_only,
            "wakeword_offline_capable": wakeword.offline_capable,
            "wakeword_streaming_audio_supported": wakeword.streaming_audio_supported,
            "wakeword_continuous_while_page_open": wakeword.continuous_while_page_open,
            "wakeword_native_background_supported": wakeword.native_background_supported,
            "wakeword_screen_off_supported": wakeword.screen_off_supported,
            "wakeword_locked_device_supported": wakeword.locked_device_supported,
            "wakeword_active_connections": wakeword_active_connections,
            "wakeword_max_buffered_frames": request.app.state.settings.wakeword_maximum_buffered_frames,
        },
        tasks=request.app.state.scheduled_task_scheduler.get_status() if hasattr(request.app.state, "scheduled_task_scheduler") else {},
    )
