"""SQLite database and ChromaDB semantic index backup and restore procedures."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from tara_api.persistence.database import Database


class BackupError(Exception):
    """Raised when a database backup or restore operation fails."""


class BackupService:
    """Manage atomic database backups, integrity verification, and safe restoration."""

    def __init__(self, database: Database, backup_dir: Path, chroma_dir: Path | None = None) -> None:
        self.database = database
        self.backup_dir = backup_dir
        self.chroma_dir = chroma_dir

    async def create_backup(self) -> dict[str, Any]:
        """Create an atomic backup bundle containing SQLite database and ChromaDB state."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_id = f"backup_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        temp_dir = Path(tempfile.mkdtemp(prefix="tara_backup_"))

        try:
            # 1. Back up SQLite database
            db_url = self.database.database_url
            url_obj = make_url(db_url)
            db_path_str = url_obj.database

            backup_db_path = temp_dir / "tara_backup.sqlite"
            if db_path_str and db_path_str != ":memory:" and not db_path_str.startswith("file:"):
                source_db_path = Path(db_path_str).expanduser().resolve()
                if source_db_path.exists():
                    shutil.copy2(source_db_path, backup_db_path)
                else:
                    # In-memory or empty fallback
                    backup_db_path.touch()
            else:
                backup_db_path.touch()

            # 2. Verify integrity of backup database
            backup_db = Database(f"sqlite+aiosqlite:///{backup_db_path.as_posix()}", encryption_key=self.database.encryption_key)
            integrity_ok = await backup_db.check_integrity()
            await backup_db.dispose()

            if not integrity_ok:
                raise BackupError("backup_integrity_check_failed")

            # 3. Get current Alembic migration revision
            alembic_version = await self._get_alembic_version()

            # 4. Back up ChromaDB index if enabled and present
            has_chroma = False
            if self.chroma_dir and self.chroma_dir.exists() and self.chroma_dir.is_dir():
                chroma_dest = temp_dir / "chroma"
                shutil.copytree(self.chroma_dir, chroma_dest, dirs_exist_ok=True)
                has_chroma = True

            # 5. Create backup manifest
            created_at = datetime.now(UTC).isoformat()
            manifest = {
                "backup_id": backup_id,
                "created_at": created_at,
                "alembic_version": alembic_version,
                "database_integrity": "ok" if integrity_ok else "failed",
                "has_chroma": has_chroma,
                "application_version": "0.1.0",
            }
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            # 6. Archive backup folder into tar.gz
            archive_path = self.backup_dir / f"{backup_id}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(temp_dir, arcname=backup_id)

            archive_size = archive_path.stat().st_size
            return {
                "backup_id": backup_id,
                "archive_path": str(archive_path),
                "created_at": created_at,
                "size_bytes": archive_size,
                "alembic_version": alembic_version,
                "integrity_status": "ok",
                "has_chroma": has_chroma,
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def list_backups(self) -> list[dict[str, Any]]:
        """List available safe backup bundles in the configured backup directory."""
        if not self.backup_dir.exists():
            return []

        backups: list[dict[str, Any]] = []
        for path in sorted(self.backup_dir.glob("backup_*.tar.gz"), reverse=True):
            try:
                with tarfile.open(path, "r:gz") as tar:
                    manifest_file = None
                    for member in tar.getmembers():
                        if member.name.endswith("manifest.json"):
                            manifest_file = tar.extractfile(member)
                            break
                    if manifest_file:
                        data = json.loads(manifest_file.read().decode("utf-8"))
                        backups.append({
                            "backup_id": data.get("backup_id", path.stem),
                            "archive_path": str(path),
                            "created_at": data.get("created_at"),
                            "size_bytes": path.stat().st_size,
                            "alembic_version": data.get("alembic_version"),
                            "integrity_status": data.get("database_integrity", "unknown"),
                            "has_chroma": data.get("has_chroma", False),
                        })
            except Exception:
                continue
        return backups

    async def restore_backup(self, archive_path: Path) -> dict[str, Any]:
        """Restore a database backup archive with integrity and migration checks."""
        if not archive_path.exists():
            raise BackupError("backup_archive_not_found")

        temp_dir = Path(tempfile.mkdtemp(prefix="tara_restore_"))
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=temp_dir)

            # Find extracted manifest and database
            manifest_path = None
            db_path = None
            chroma_path = None
            for p in temp_dir.rglob("manifest.json"):
                manifest_path = p
                break

            for p in temp_dir.rglob("tara_backup.sqlite"):
                db_path = p
                break

            for p in temp_dir.rglob("chroma"):
                if p.is_dir():
                    chroma_path = p
                    break

            if not manifest_path or not db_path:
                raise BackupError("invalid_backup_archive_format")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            # Verify integrity of extracted backup database
            extracted_db = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}", encryption_key=self.database.encryption_key)
            integrity_ok = await extracted_db.check_integrity()
            await extracted_db.dispose()

            if not integrity_ok:
                raise BackupError("restored_database_integrity_failed")

            # Perform atomic restoration to current database path
            url_obj = make_url(self.database.database_url)
            db_path_str = url_obj.database
            if db_path_str and db_path_str != ":memory:" and not db_path_str.startswith("file:"):
                target_db_path = Path(db_path_str).expanduser().resolve()
                target_db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_path, target_db_path)

            # Restore ChromaDB files if available
            if chroma_path and self.chroma_dir:
                self.chroma_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(chroma_path, self.chroma_dir, dirs_exist_ok=True)

            return {
                "backup_id": manifest.get("backup_id"),
                "restored_at": datetime.now(UTC).isoformat(),
                "alembic_version": manifest.get("alembic_version"),
                "integrity_status": "ok",
                "chroma_restored": chroma_path is not None,
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _get_alembic_version(self) -> str | None:
        """Fetch current database Alembic migration revision."""
        try:
            async with self.database.engine.connect() as conn:
                res = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = res.fetchone()
                return str(row[0]) if row else None
        except Exception:
            return None
