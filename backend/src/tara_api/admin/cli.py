"""Command-line administrative utilities for deployment management."""

import asyncio
import json
import sys
from pathlib import Path

from tara_api.admin.backup import BackupService
from tara_api.admin.diagnostics import DiagnosticsService
from tara_api.config.settings import Settings
from tara_api.main import create_app
from tara_api.persistence.database import Database


def backup_cli() -> None:
    """Run interactive or scripted SQLite and ChromaDB backup."""
    async def _run() -> None:
        settings = Settings()
        db_key = settings.database_encryption_key.get_secret_value() or None
        db = Database(settings.database_url, encryption_key=db_key)
        backup_dir = Path(settings.backup_directory)
        chroma_dir = Path(settings.memory_chroma_directory) if settings.memory_semantic_provider == "chromadb" else None

        service = BackupService(db, backup_dir, chroma_dir)
        result = await service.create_backup()
        await db.dispose()
        print(json.dumps(result, indent=2))

    asyncio.run(_run())


def restore_cli() -> None:
    """Restore SQLite database and ChromaDB state from a backup archive."""
    if len(sys.argv) < 2:
        print("Usage: tara-restore <path-to-backup-archive.tar.gz>")
        sys.exit(1)

    archive_path = Path(sys.argv[1])

    async def _run() -> None:
        settings = Settings()
        db_key = settings.database_encryption_key.get_secret_value() or None
        db = Database(settings.database_url, encryption_key=db_key)
        backup_dir = Path(settings.backup_directory)
        chroma_dir = Path(settings.memory_chroma_directory) if settings.memory_semantic_provider == "chromadb" else None

        service = BackupService(db, backup_dir, chroma_dir)
        result = await service.restore_backup(archive_path)
        await db.dispose()
        print(json.dumps(result, indent=2))

    asyncio.run(_run())


def diagnostics_cli() -> None:
    """Output redacted deployment diagnostics report."""
    async def _run() -> None:
        settings = Settings()
        app = create_app(settings=settings)
        service = DiagnosticsService(app)
        report = await service.generate_report()
        if hasattr(app.state, "database"):
            await app.state.database.dispose()
        print(json.dumps(report, indent=2))

    asyncio.run(_run())
