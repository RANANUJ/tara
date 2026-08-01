"""FastAPI application factory for the Tara backend bootstrap."""
# ruff: noqa: I001

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import uvicorn
from fastapi import FastAPI

from tara_api.api.errors import install_error_handlers
from tara_api.api.middleware import install_request_middleware
from tara_api.api.v1.auth import router as auth_router
from tara_api.api.v1.health import router as health_router
from tara_api.api.v1.status import router as status_router
from tara_api.api.v1.websocket import router as websocket_router
from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.config.settings import Settings, get_settings
from tara_api.observability.application import ApplicationStatusProvider
from tara_api.observability.health import DependencyHealthRegistry, SystemClock, implemented_health_checks
from tara_api.observability.logging import configure_logging, log_settings_loaded
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database
from tara_api.transport.registry import InMemoryConnectionRegistry, RegistryEventPublisher
from tara_api.transport.tickets import InMemoryConnectionTicketService
from tara_api.stt.service import FakeSpeechToTextProvider, FasterWhisperSpeechToTextProvider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and dispose the database without applying migrations at runtime."""
    database: Database = app.state.database
    await database.start()
    try:
        yield
    finally:
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
    app.state.connection_ticket_service = InMemoryConnectionTicketService(
        app.state.authentication_service,
        timedelta(seconds=resolved_settings.websocket_ticket_seconds),
    )
    app.state.connection_registry = InMemoryConnectionRegistry(resolved_settings.websocket_max_connections_per_session)
    app.state.websocket_event_publisher = RegistryEventPublisher(app.state.connection_registry)
    app.state.stt_provider = FakeSpeechToTextProvider() if resolved_settings.stt_provider == "fake" else FasterWhisperSpeechToTextProvider(resolved_settings.stt_model, resolved_settings.stt_device, resolved_settings.stt_compute_type)
    app.state.health_registry = DependencyHealthRegistry(
        implemented_health_checks(app.state.database),
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
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(websocket_router, prefix="/api/v1")
    return app


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
