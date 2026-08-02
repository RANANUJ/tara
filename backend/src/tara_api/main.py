"""FastAPI application factory for the Tara backend bootstrap."""
# ruff: noqa: I001

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import uvicorn
from fastapi import FastAPI

from tara_api.api.errors import install_error_handlers
from tara_api.api.middleware import install_request_middleware
from tara_api.api.v1.auth import router as auth_router
from tara_api.api.v1.actions import router as actions_router
from tara_api.api.v1.health import router as health_router
from tara_api.api.v1.status import router as status_router
from tara_api.api.v1.websocket import router as websocket_router
from tara_api.api.v1.websocket import submit_final_transcript
from tara_api.agent.context import DatabaseStructuredContextProvider
from tara_api.agent.context_policy import ContextSensitivityPolicy
from tara_api.agent.fake import FakeLanguageModelProvider
from tara_api.agent.health import LocalLanguageModelHealthProvider
from tara_api.agent.ollama import OllamaLanguageModelProvider
from tara_api.agent.prompt import DefaultPromptBuilder
from tara_api.agent.registry import AgentRequestRegistry
from tara_api.agent.routing import DeterministicIntentRouter
from tara_api.agent.service import AgentService
from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.config.settings import Settings, get_settings
from tara_api.domain.agent import ContextBudget, ContextSensitivity, LanguageModelProvider, ProviderHealthState
from tara_api.domain.health import DependencyName, HealthSeverity, HealthState
from tara_api.domain.stt import TranscriptionJob
from tara_api.domain.tts import SpeechFormat, SpeechVoice, TextToSpeechProvider
from tara_api.observability.application import ApplicationStatusProvider
from tara_api.observability.health import CallableHealthCheck, DependencyHealthRegistry, SystemClock, implemented_health_checks
from tara_api.observability.logging import configure_logging, log_settings_loaded
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.agent_store import SqlAlchemyAgentPersistenceStore
from tara_api.persistence.database import Database
from tara_api.persistence.safety_store import SqlAlchemySafetyStore
from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.capabilities.service import CapabilityService
from tara_api.domain.capabilities import CapabilityState
from tara_api.domain.models import PermissionScope
from tara_api.safety.clock import SystemClock as SafetySystemClock
from tara_api.safety.confirmations import DeterministicConfirmationService
from tara_api.safety.permissions import DefaultDenyPermissionService
from tara_api.safety.policy import DeterministicActionPolicyService
from tara_api.safety.tool_executor import SafetyToolExecutor
from tara_api.memory.lifecycle import MemoryLifecycleScheduler, MemoryLifecycleService
from tara_api.memory.exports import MemoryExportService
from tara_api.memory.semantic import ChromaSemanticMemoryIndex, UnavailableSemanticMemoryIndex
from tara_api.memory.service import MemoryService
from tara_api.transport.registry import InMemoryConnectionRegistry, RegistryEventPublisher
from tara_api.transport.tickets import InMemoryConnectionTicketService
from tara_api.stt.faster_whisper import FasterWhisperSpeechToTextProvider
from tara_api.stt.service import FakeSpeechToTextProvider, InMemoryTranscriptionJobs
from tara_api.stt.health import SttHealthProvider
from tara_api.tts.elevenlabs import ElevenLabsTextToSpeechProvider
from tara_api.tts.fake import FakeTextToSpeechProvider
from tara_api.tts.health import LocalTextToSpeechHealthProvider
from tara_api.tts.piper import PiperTextToSpeechProvider
from tara_api.tts.registry import SynthesisRequestRegistry
from tara_api.tts.service import TextToSpeechService
from tara_api.tts.source import InMemoryApprovedAgentResponseSource
from tara_api.domain.wakeword import WakeWordConfiguration, WakeWordDetector
from tara_api.wakeword.fake import FakeWakeWordDetector
from tara_api.wakeword.health import LocalWakeWordHealthProvider
from tara_api.wakeword.service import WakeWordService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and dispose the database without applying migrations at runtime."""
    database: Database = app.state.database
    await database.start()
    if app.state.settings.memory_scheduler_enabled:
        app.state.memory_lifecycle_scheduler.start()
    try:
        yield
    finally:
        app.state.memory_lifecycle_scheduler.shutdown()
        await app.state.tts_service.shutdown()
        await app.state.agent_service.shutdown()
        await database.dispose()


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    """Create the M6 API application without product features."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)
    log_settings_loaded(resolved_settings)

    is_production = resolved_settings.environment == "production"
    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database or Database(resolved_settings.database_url)
    filesystem_tool: AllowlistedFilesystemListTool | None = None
    filesystem_state = CapabilityState.DISABLED
    if resolved_settings.tools_filesystem_read_enabled:
        try:
            filesystem_tool = AllowlistedFilesystemListTool(tuple(Path(root) for root in resolved_settings.tools_filesystem_read_roots))
            filesystem_state = CapabilityState.AVAILABLE
        except (OSError, ValueError):
            filesystem_state = CapabilityState.UNAVAILABLE
    app.state.capability_registry = CapabilityRegistry(filesystem_tool, filesystem_state)
    app.state.safety_store = SqlAlchemySafetyStore(app.state.database)
    app.state.memory_semantic_index = (
        ChromaSemanticMemoryIndex(Path(resolved_settings.memory_chroma_directory))
        if resolved_settings.memory_semantic_provider == "chromadb"
        else UnavailableSemanticMemoryIndex()
    )
    app.state.memory_service = MemoryService(
        app.state.database,
        app.state.memory_semantic_index,
        now=lambda: datetime.now(UTC),
    )
    app.state.memory_lifecycle = MemoryLifecycleService(app.state.memory_service)
    app.state.memory_lifecycle_scheduler = MemoryLifecycleScheduler(app.state.memory_lifecycle)
    app.state.memory_exports = MemoryExportService(app.state.memory_service, now=lambda: datetime.now(UTC))
    app.state.authentication_store = SqlAlchemyAuthenticationStore(app.state.database)
    app.state.authentication_service = AuthenticationService(
        app.state.authentication_store,
        app.state.authentication_store,
        Argon2idPasswordHasher(),
        SecureSessionTokenGenerator(),
        InMemoryLoginRateLimiter(),
        lambda: datetime.now(UTC),
        timedelta(minutes=resolved_settings.session_absolute_minutes),
        timedelta(minutes=resolved_settings.session_idle_minutes),
    )
    app.state.confirmation_service = DeterministicConfirmationService(
        app.state.safety_store,
        SafetySystemClock(),
        context_validator=app.state.authentication_service,
    )
    granted_scopes = (PermissionScope("filesystem.read"),) if filesystem_tool is not None else ()
    app.state.tool_executor = SafetyToolExecutor(
        app.state.capability_registry,
        DefaultDenyPermissionService(granted_scopes),
        DeterministicActionPolicyService(),
        app.state.confirmation_service,
        app.state.safety_store,
        SafetySystemClock(),
    )
    app.state.capability_service = CapabilityService(
        app.state.capability_registry,
        app.state.tool_executor,
        app.state.authentication_service,
    )
    app.state.connection_ticket_service = InMemoryConnectionTicketService(
        app.state.authentication_service,
        timedelta(seconds=resolved_settings.websocket_ticket_seconds),
    )
    app.state.connection_registry = InMemoryConnectionRegistry(resolved_settings.websocket_max_connections_per_session)
    app.state.websocket_event_publisher = RegistryEventPublisher(app.state.connection_registry)
    app.state.llm_provider = _language_model_provider(resolved_settings)
    app.state.llm_health = LocalLanguageModelHealthProvider(
        app.state.llm_provider,
        required=resolved_settings.llm_required,
        environment=resolved_settings.environment,
        timeout_seconds=resolved_settings.health_check_timeout_ms / 1000,
    )

    async def llm_health_dependency() -> tuple[HealthState, str | None]:
        snapshot = await app.state.llm_health.snapshot()
        if snapshot.ready:
            return HealthState.HEALTHY, None
        if snapshot.state == ProviderHealthState.DISABLED:
            return HealthState.HEALTHY, "Language model is disabled."
        if snapshot.state == ProviderHealthState.DEGRADED:
            return HealthState.DEGRADED, "Language model is degraded."
        return HealthState.UNAVAILABLE, "Language model is unavailable."

    app.state.llm_health_dependency = llm_health_dependency
    context_budget = ContextBudget(
        resolved_settings.agent_context_memory_limit,
        resolved_settings.agent_context_recent_turn_limit,
        resolved_settings.agent_context_memory_item_char_limit,
        resolved_settings.agent_context_recent_turn_char_limit,
        resolved_settings.agent_context_total_char_limit,
        resolved_settings.agent_context_estimated_token_limit,
    )
    context_policy = ContextSensitivityPolicy(
        ContextSensitivity(value) for value in resolved_settings.agent_context_allowed_sensitivities
    )
    app.state.agent_registry = AgentRequestRegistry(
        maximum_queued=resolved_settings.agent_max_queued_requests,
        maximum_concurrent=resolved_settings.agent_max_concurrent_requests,
        maximum_per_connection=resolved_settings.agent_max_requests_per_connection,
        maximum_per_session=resolved_settings.agent_max_requests_per_session,
        maximum_per_owner=resolved_settings.agent_max_requests_per_owner,
        maximum_terminal_records=resolved_settings.agent_max_terminal_records,
        terminal_retention=timedelta(seconds=resolved_settings.agent_terminal_retention_seconds),
    )
    app.state.agent_service = AgentService(
        registry=app.state.agent_registry,
        persistence=SqlAlchemyAgentPersistenceStore(app.state.database),
        session_validator=app.state.authentication_service,
        router=DeterministicIntentRouter(resolved_settings.agent_intent_confidence_threshold),
        context_provider=lambda owner_id: DatabaseStructuredContextProvider(
            app.state.database,
            owner_id=owner_id,
            budget=context_budget,
            policy=context_policy,
            now=lambda: datetime.now(UTC),
        ),
        prompt_builder=DefaultPromptBuilder(),
        model_provider=app.state.llm_provider,
        context_token_budget=resolved_settings.llm_context_token_budget,
        output_token_budget=resolved_settings.llm_output_token_budget,
        timeout_seconds=resolved_settings.agent_request_timeout_seconds,
    )
    app.state.tts_provider = _text_to_speech_provider(resolved_settings)
    app.state.tts_response_source = InMemoryApprovedAgentResponseSource(
        resolved_settings.tts_max_terminal_records
    )
    app.state.tts_registry = SynthesisRequestRegistry(
        maximum_queued=resolved_settings.tts_max_queued_requests,
        maximum_concurrent=resolved_settings.tts_max_concurrent_requests,
        maximum_per_connection=resolved_settings.tts_max_requests_per_connection,
        maximum_per_session=resolved_settings.tts_max_requests_per_session,
        maximum_per_owner=resolved_settings.tts_max_requests_per_owner,
        maximum_terminal_records=resolved_settings.tts_max_terminal_records,
        terminal_retention=timedelta(seconds=resolved_settings.tts_terminal_retention_seconds),
        maximum_retained_audio_bytes=resolved_settings.tts_max_retained_audio_bytes,
    )
    app.state.tts_service = TextToSpeechService(
        registry=app.state.tts_registry,
        provider=app.state.tts_provider,
        session_validator=app.state.authentication_service,
        response_source=app.state.tts_response_source,
        timeout_seconds=resolved_settings.tts_timeout_seconds,
        maximum_chunk_bytes=resolved_settings.tts_max_chunk_bytes,
    )
    app.state.tts_health = LocalTextToSpeechHealthProvider(
        app.state.tts_provider,
        required=resolved_settings.tts_required,
        environment=resolved_settings.environment,
        language_mode=resolved_settings.tts_language_mode,
        timeout_seconds=resolved_settings.health_check_timeout_ms / 1000,
    )
    wakeword_configuration = WakeWordConfiguration(
        provider=resolved_settings.wakeword_provider,
        phrase=resolved_settings.wakeword_phrase,
        enabled=resolved_settings.wakeword_enabled,
        confidence_threshold=resolved_settings.wakeword_confidence_threshold,
        minimum_consecutive_detections=resolved_settings.wakeword_minimum_consecutive_detections,
        cooldown_seconds=resolved_settings.wakeword_cooldown_seconds,
        debounce_seconds=resolved_settings.wakeword_debounce_seconds,
        frame_duration_ms=resolved_settings.wakeword_frame_duration_ms,
        maximum_buffered_frames=resolved_settings.wakeword_maximum_buffered_frames,
        language_mode=resolved_settings.wakeword_language_mode,
        foreground_only=resolved_settings.wakeword_foreground_only,
        maximum_frame_age_seconds=resolved_settings.wakeword_maximum_frame_age_seconds,
    )
    app.state.wakeword_provider = _wakeword_provider(resolved_settings)
    app.state.wakeword_service = WakeWordService(
        wakeword_configuration,
        app.state.wakeword_provider,
        session_validator=app.state.authentication_service,
    )
    app.state.wakeword_health = LocalWakeWordHealthProvider(
        wakeword_configuration,
        app.state.wakeword_provider,
        required=resolved_settings.wakeword_required,
        environment=resolved_settings.environment,
        timeout_seconds=resolved_settings.health_check_timeout_ms / 1000,
    )
    app.state.stt_provider = None if resolved_settings.stt_provider == "disabled" else FakeSpeechToTextProvider() if resolved_settings.stt_provider == "fake" else FasterWhisperSpeechToTextProvider(resolved_settings.stt_model, resolved_settings.stt_device, resolved_settings.stt_compute_type, language_hint=resolved_settings.stt_language_hint, local_model_directory=resolved_settings.stt_local_model_directory)  # noqa: E501

    async def publish_stt_event(job: TranscriptionJob, event_type: str, payload: dict[str, object]) -> None:
        request = job.request
        connection = await app.state.connection_registry.get(request.connection_id)
        if connection is None:
            return
        context = connection.context
        if context.owner_id != request.owner_id or context.session_id != request.session_id or context.connection_id != request.connection_id:
            return
        await connection.send_event(event_type, {"transcription_id": str(request.transcription_id), "audio_session_id": str(request.audio_session_id), "turn_id": str(request.turn_id), **payload})
        transcript_text = payload.get("text")
        if event_type == "transcript.final" and isinstance(transcript_text, str):
            await submit_final_transcript(connection, transcript_text, request.transcription_id)

    app.state.stt_jobs = InMemoryTranscriptionJobs(app.state.stt_provider, publish_stt_event, resolved_settings.stt_max_queued_jobs, resolved_settings.stt_max_concurrent_jobs, resolved_settings.stt_timeout_seconds)
    app.state.stt_health = SttHealthProvider(app.state.stt_provider, app.state.stt_jobs, required=resolved_settings.stt_required, environment=resolved_settings.environment, language_mode=resolved_settings.stt_language_hint or "auto", partial_mode=resolved_settings.stt_partial_mode, max_queue=resolved_settings.stt_max_queued_jobs, max_concurrency=resolved_settings.stt_max_concurrent_jobs, timeout_seconds=resolved_settings.stt_health_timeout_ms / 1000)  # noqa: E501
    app.state.health_registry = DependencyHealthRegistry(
        implemented_health_checks(
            app.state.database,
            CallableHealthCheck(DependencyName.STT, HealthSeverity.REQUIRED if resolved_settings.stt_required else HealthSeverity.OPTIONAL, app.state.stt_health.dependency),
            CallableHealthCheck(DependencyName.LLM, HealthSeverity.REQUIRED if resolved_settings.llm_required else HealthSeverity.OPTIONAL, app.state.llm_health_dependency),
            CallableHealthCheck(DependencyName.TTS, HealthSeverity.REQUIRED if resolved_settings.tts_required else HealthSeverity.OPTIONAL, app.state.tts_health.dependency),
            CallableHealthCheck(DependencyName.WAKEWORD, HealthSeverity.REQUIRED if resolved_settings.wakeword_required else HealthSeverity.OPTIONAL, app.state.wakeword_health.dependency),
        ),
        SystemClock(),
        resolved_settings.health_check_timeout_ms / 1000,
    )
    app.state.status_provider = ApplicationStatusProvider(
        app.state.health_registry,
        resolved_settings.app_name,
        resolved_settings.app_version,
        resolved_settings.environment,
        datetime.now(UTC),
        resolved_settings.build_revision,
    )
    install_request_middleware(app)
    install_error_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(actions_router, prefix="/api/v1")
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(websocket_router, prefix="/api/v1")
    return app


def _language_model_provider(settings: Settings) -> LanguageModelProvider | None:
    if settings.llm_provider == "disabled":
        return None
    if settings.llm_provider == "fake":
        return FakeLanguageModelProvider(
            model_identifier="fake-local",
            timeout_seconds=settings.llm_timeout_seconds,
            environment=settings.environment,
        )
    return OllamaLanguageModelProvider(
        settings.ollama_base_url,
        settings.ollama_model,
        timeout_seconds=settings.llm_timeout_seconds,
        context_token_budget=settings.llm_context_token_budget,
        output_token_budget=settings.llm_output_token_budget,
        temperature=settings.llm_temperature,
        streaming=settings.llm_streaming,
    )


def _text_to_speech_provider(settings: Settings) -> TextToSpeechProvider | None:
    if settings.tts_provider == "disabled":
        return None
    voice = SpeechVoice(settings.tts_voice_identifier or "local-voice")
    output_format = SpeechFormat(
        sample_rate=settings.tts_output_sample_rate,
        channels=settings.tts_output_channels,
    )
    if settings.tts_provider == "fake":
        return cast(TextToSpeechProvider, FakeTextToSpeechProvider(
            voice=voice,
            timeout_seconds=settings.tts_timeout_seconds,
            environment=settings.environment,
        ))
    if settings.tts_provider == "piper":
        return cast(TextToSpeechProvider, PiperTextToSpeechProvider(
            settings.tts_piper_executable,
            settings.tts_piper_voice_model_path or "",
            voice=voice,
            output_format=output_format,
            voice_config_path=settings.tts_piper_voice_config_path,
            timeout_seconds=settings.tts_timeout_seconds,
        ))
    return cast(TextToSpeechProvider, ElevenLabsTextToSpeechProvider(
        settings.elevenlabs_api_key,
        voice,
        settings.elevenlabs_model,
        output_format=output_format,
        timeout_seconds=settings.tts_timeout_seconds,
    ))


def _wakeword_provider(settings: Settings) -> WakeWordDetector | None:
    if settings.wakeword_provider == "disabled":
        return None
    return FakeWakeWordDetector(environment=settings.environment)


app = create_app()


def run() -> None:
    """Run the bootstrap API using local-only development defaults."""
    settings = get_settings()
    uvicorn.run(
        "tara_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )
