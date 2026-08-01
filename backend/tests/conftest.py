"""Shared isolated database fixtures for Tara API tests."""

from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tara_api.config.settings import Settings
from tara_api.main import create_app
from tara_api.persistence.database import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def migrate_database(database_path: Path) -> None:
    """Upgrade an empty SQLite database through the tracked Alembic history."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Provide one empty SQLite file per test."""
    return tmp_path / "tara-test.db"


@pytest.fixture
def database_url(database_path: Path) -> str:
    """Provide an async SQLite URL for the per-test database file."""
    return f"sqlite+aiosqlite:///{database_path.as_posix()}"


@pytest_asyncio.fixture
async def database(database_path: Path, database_url: str) -> Database:
    """Create and migrate an isolated database for repository tests."""
    migrate_database(database_path)
    instance = Database(database_url)
    await instance.start()
    try:
        yield instance
    finally:
        await instance.dispose()


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Provide deterministic settings without reading a local .env file."""
    return Settings(
        _env_file=None,
        environment="test",
        service_secret="test-secret",
        database_url=database_url,
    )


@pytest.fixture
def app(settings: Settings, database: Database) -> FastAPI:
    """Create an isolated FastAPI application for each test."""
    return create_app(settings, database)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a synchronous client for health endpoint tests."""
    with TestClient(app) as test_client:
        yield test_client
