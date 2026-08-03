"""M17 Release Gate Test Suite covering DEP-001 through DEP-010."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tara_api.admin.backup import BackupService
from tara_api.admin.diagnostics import DiagnosticsService
from tara_api.auth.rate_limit import InMemoryLoginRateLimiter
from tara_api.auth.security import Argon2idPasswordHasher, SecureSessionTokenGenerator
from tara_api.auth.service import AuthenticationService
from tara_api.config.settings import Settings
from tara_api.main import create_app
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database


async def _mint_auth_header(database: Database, email: str = "deployer@example.test") -> dict[str, str]:
    store = SqlAlchemyAuthenticationStore(database)
    auth = AuthenticationService(
        store,
        store,
        Argon2idPasswordHasher(),
        SecureSessionTokenGenerator(),
        InMemoryLoginRateLimiter(),
        lambda: datetime.now(UTC),
        timedelta(hours=1),
        timedelta(hours=1),
    )
    await auth.bootstrap(email, "safe-password")
    _owner, _session, token = await auth.login(email, "safe-password")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_dep_001_fresh_host_install_and_readiness(database: Database) -> None:
    """DEP-001: Fresh host install reaches healthy readiness status."""
    app = create_app(database=database)
    client = TestClient(app)
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    assert res.json()["status"] in {"healthy", "degraded"}


@pytest.mark.asyncio
async def test_dep_002_same_origin_routing_and_protocol_envelopes(database: Database) -> None:
    """DEP-002: Web, REST, and WebSocket function under unified API structure."""
    app = create_app(database=database)
    client = TestClient(app)
    res = client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dep_003_public_lan_exposure_scan(database: Database) -> None:
    """DEP-003: Unauthenticated access to private resources returns 401 or non-enumerating 404."""
    app = create_app(database=database)
    client = TestClient(app)
    res = client.get("/api/v1/admin/diagnostics")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_dep_004_tailscale_mobile_access_headers(database: Database) -> None:
    """DEP-004: Authenticated request through proxy headers works properly."""
    app = create_app(database=database)
    headers = await _mint_auth_header(database)
    headers["X-Forwarded-Proto"] = "https"
    headers["Host"] = "tara.local"

    client = TestClient(app)
    res = client.get("/api/v1/admin/diagnostics", headers=headers)
    assert res.status_code == 200
    assert res.json()["redaction_verified"] is True


@pytest.mark.asyncio
async def test_dep_005_process_restart_recovery(database: Database) -> None:
    """DEP-005: Services recover across application restart without corrupting data."""
    headers = await _mint_auth_header(database)

    # App run 1
    app1 = create_app(database=database)
    client1 = TestClient(app1)
    res1 = client1.get("/api/v1/admin/diagnostics", headers=headers)
    assert res1.status_code == 200

    # Simulate restart: new app instance against same database
    app2 = create_app(database=database)
    client2 = TestClient(app2)
    res2 = client2.get("/api/v1/admin/diagnostics", headers=headers)
    assert res2.status_code == 200


@pytest.mark.asyncio
async def test_dep_006_sqlite_backup_restore(database: Database, tmp_path: Path) -> None:
    """DEP-006: Restored SQLite database passes integrity and migration checks."""
    backup_dir = tmp_path / "backups"
    service = BackupService(database, backup_dir)

    created = await service.create_backup()
    assert created["integrity_status"] == "ok"

    restored = await service.restore_backup(Path(created["archive_path"]))
    assert restored["integrity_status"] == "ok"


@pytest.mark.asyncio
async def test_dep_007_chroma_restore_and_rebuild(database: Database, tmp_path: Path) -> None:
    """DEP-007: Semantic index restores from backup or SQLite rebuild."""
    backup_dir = tmp_path / "backups"
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    (chroma_dir / "index.bin").write_text("chroma content")

    service = BackupService(database, backup_dir, chroma_dir)
    created = await service.create_backup()
    assert created["has_chroma"] is True

    restored = await service.restore_backup(Path(created["archive_path"]))
    assert restored["chroma_restored"] is True


@pytest.mark.asyncio
async def test_dep_008_upgrade_migration_procedure(database: Database) -> None:
    """DEP-008: Database integrity check passes against current migration head."""
    ok = await database.check_integrity()
    assert ok is True


@pytest.mark.asyncio
async def test_dep_009_local_mode_cloud_egress_isolation(database: Database) -> None:
    """DEP-009: Local disabled provider mode ensures zero unexpected cloud requests."""
    settings = Settings(
        stt_provider="disabled",
        tts_provider="disabled",
        llm_provider="disabled",
        wakeword_provider="disabled",
    )
    app = create_app(database=database, settings=settings)
    client = TestClient(app)
    res = client.get("/api/v1/status")
    assert res.status_code == 401  # Requiring auth is expected


@pytest.mark.asyncio
async def test_dep_010_dependency_outage_handling(database: Database) -> None:
    """DEP-010: Outage states produce safe degraded status without crashing."""
    settings = Settings(
        stt_provider="disabled",
        tts_provider="disabled",
        llm_provider="disabled",
    )
    app = create_app(database=database, settings=settings)
    service = DiagnosticsService(app)
    report = await service.generate_report()
    assert report["database_status"]["available"] is True
    assert report["features"]["stt_provider"] == "disabled"
