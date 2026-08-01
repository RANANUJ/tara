"""Tests that the tracked Alembic history creates a usable empty database."""

import sqlite3
from pathlib import Path

from conftest import migrate_database


def test_initial_migration_upgrades_an_empty_database(database_path: Path) -> None:
    migrate_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {
        "alembic_version",
        "conversations",
        "conversation_turns",
        "structured_memories",
        "permission_settings",
        "pending_confirmations",
        "confirmation_consumptions",
        "audit_events",
        "scheduler_job_metadata",
        "safe_service_configurations",
    }.issubset(table_names)
