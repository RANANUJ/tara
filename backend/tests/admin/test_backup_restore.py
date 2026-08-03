"""Tests for M17 database backup, integrity verification, and restoration."""

from pathlib import Path

import pytest

from tara_api.admin.backup import BackupError, BackupService
from tara_api.persistence.database import Database


@pytest.mark.asyncio
async def test_backup_creation_and_integrity_check(database: Database, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    (chroma_dir / "index_file.bin").write_text("chroma index data")

    service = BackupService(database, backup_dir, chroma_dir)
    res = await service.create_backup()

    assert res["integrity_status"] == "ok"
    assert res["has_chroma"] is True
    assert Path(res["archive_path"]).exists()

    listed = await service.list_backups()
    assert len(listed) == 1
    assert listed[0]["backup_id"] == res["backup_id"]


@pytest.mark.asyncio
async def test_backup_restoration_lifecycle(database: Database, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    chroma_dir = tmp_path / "chroma"

    service = BackupService(database, backup_dir, chroma_dir)
    created = await service.create_backup()

    archive_path = Path(created["archive_path"])
    restored = await service.restore_backup(archive_path)

    assert restored["integrity_status"] == "ok"
    assert restored["backup_id"] == created["backup_id"]


@pytest.mark.asyncio
async def test_backup_restoration_invalid_archive(database: Database, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    service = BackupService(database, backup_dir)

    invalid_archive = tmp_path / "nonexistent.tar.gz"
    with pytest.raises(BackupError):
        await service.restore_backup(invalid_archive)
