"""FastAPI application factory for the Tara backend bootstrap."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import uvicorn
from fastapi import FastAPI

from tara_api.api.v1.auth import router as auth_router
from tara_api.api.v1.health import router as health_router
from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.config.settings import Settings, get_settings
from tara_api.observability.logging import configure_logging, log_settings_loaded
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database


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
    """Create the M2 API application without product services."""
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
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
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
