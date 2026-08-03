"""Tests for M17 redacted operational diagnostics."""

import pytest

from tara_api.admin.diagnostics import DiagnosticsService
from tara_api.config.settings import Settings
from tara_api.main import create_app
from tara_api.persistence.database import Database


@pytest.mark.asyncio
async def test_diagnostics_report_generation(database: Database) -> None:
    app = create_app(database=database)
    service = DiagnosticsService(app)
    report = await service.generate_report()

    assert report["application_name"] == "Tara API"
    assert report["database_status"]["available"] is True
    assert report["database_status"]["integrity_ok"] is True
    assert report["redaction_verified"] is True
    assert "system_info" in report
    assert "features" in report


@pytest.mark.asyncio
async def test_diagnostics_redaction_invariant(database: Database) -> None:
    settings = Settings(
        service_secret="super-secret-key-12345",
        task_payload_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        database_encryption_key="db-secret-key-999",
    )
    app = create_app(database=database, settings=settings)
    service = DiagnosticsService(app)
    report = await service.generate_report()

    report_str = str(report)
    assert "super-secret-key-12345" not in report_str
    assert "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=" not in report_str
    assert "db-secret-key-999" not in report_str
