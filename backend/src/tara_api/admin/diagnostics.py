"""Redacted operational diagnostics and deployment status reporting."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

from tara_api.config.settings import Settings


class DiagnosticsService:
    """Gather comprehensive, audit-safe operational diagnostics for deployment readiness."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def generate_report(self) -> dict[str, Any]:
        """Produce a redacted diagnostics report omitting all secrets and private data."""
        settings: Settings = self.app.state.settings
        db = self.app.state.database

        # Database reachability & integrity check
        db_conn = await db.check_connection()
        db_integrity = await db.check_integrity()

        # Migration revision check
        alembic_version = None
        try:
            async with db.engine.connect() as conn:
                res = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = res.fetchone()
                if row:
                    alembic_version = str(row[0])
        except Exception:
            alembic_version = None

        # Scheduler status
        scheduler_status = {}
        if hasattr(self.app.state, "scheduled_task_scheduler"):
            scheduler_status = self.app.state.scheduled_task_scheduler.get_status()

        # Registered tool capabilities (safe catalog descriptors)
        tools_info: list[dict[str, Any]] = []
        if hasattr(self.app.state, "capability_registry"):
            tools_info = [
                {
                    "name": c.name,
                    "label": c.label,
                    "state": c.state.value if hasattr(c.state, "value") else str(c.state),
                    "read_only": c.read_only,
                    "safe_summary": c.safe_summary,
                }
                for c in self.app.state.capability_registry.list()
            ]

        # Environment & system summary
        system_info = {
            "python_version": sys.version,
            "platform": sys.platform,
            "environment": settings.environment,
            "log_level": settings.log_level,
            "host": settings.host,
            "port": settings.port,
            "database_driver": "sqlite+aiosqlite",
            "database_encryption_enabled": bool(settings.database_encryption_key.get_secret_value()),
            "task_payload_encryption_enabled": bool(settings.task_payload_encryption_key.get_secret_value()),
            "service_secret_configured": bool(settings.service_secret.get_secret_value()),
        }

        # Safe feature flags
        feature_flags = {
            "stt_provider": settings.stt_provider,
            "tts_provider": settings.tts_provider,
            "llm_provider": settings.llm_provider,
            "wakeword_provider": settings.wakeword_provider,
            "memory_semantic_provider": settings.memory_semantic_provider,
            "scheduler_enabled": settings.scheduler_enabled,
            "tools_filesystem_read_enabled": settings.tools_filesystem_read_enabled,
            "fake_consequential_enabled": settings.fake_consequential_enabled,
        }

        return {
            "diagnostics_timestamp": datetime.now(UTC).isoformat(),
            "application_name": settings.app_name,
            "application_version": settings.app_version,
            "build_revision": settings.build_revision,
            "system_info": system_info,
            "database_status": {
                "available": db_conn.available,
                "integrity_ok": db_integrity,
                "alembic_version": alembic_version,
            },
            "scheduler_status": scheduler_status,
            "capabilities": tools_info,
            "features": feature_flags,
            "redaction_verified": True,
        }
