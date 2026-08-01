"""FastAPI application factory for the Tara backend bootstrap."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from tara_api.api.v1.health import router as health_router
from tara_api.config.settings import Settings, get_settings
from tara_api.observability.logging import configure_logging, log_settings_loaded
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
    app.include_router(health_router, prefix="/api/v1")
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
