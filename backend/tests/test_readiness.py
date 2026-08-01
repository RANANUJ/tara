"""Tests for database-aware readiness behavior."""

from fastapi.testclient import TestClient

from tara_api.config.settings import Settings
from tara_api.main import create_app
from tara_api.persistence.database import DatabaseHealth


class UnavailableDatabase:
    """Minimal database double used to exercise an unavailable readiness response."""

    async def start(self) -> None:
        return None

    async def dispose(self) -> None:
        return None

    async def check_connection(self) -> DatabaseHealth:
        return DatabaseHealth(available=False)


def test_readiness_reports_database_unavailable() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        service_secret="test-secret",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings, UnavailableDatabase())

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "dependencies": [
            {"name": "application", "status": "ready"},
            {"name": "database", "status": "unavailable"},
        ],
    }
