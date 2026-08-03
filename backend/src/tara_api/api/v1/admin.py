"""Authenticated administrative, backup/restore, and deployment diagnostics REST router."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from tara_api.admin.backup import BackupError, BackupService
from tara_api.admin.diagnostics import DiagnosticsService
from tara_api.api.v1.auth import authenticated_context
from tara_api.domain.auth import AuthenticatedOwnerContext

router = APIRouter(prefix="/admin", tags=["admin"])


class RestoreRequest(BaseModel):
    backup_id: str


@router.post("/backups", status_code=status.HTTP_201_CREATED)
async def create_backup(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, Any]:
    """Create an atomic backup bundle of SQLite database and ChromaDB state."""
    db = request.app.state.database
    settings = request.app.state.settings
    backup_dir = Path(settings.backup_directory)
    chroma_dir = Path(settings.memory_chroma_directory) if settings.memory_semantic_provider == "chromadb" else None

    service = BackupService(db, backup_dir, chroma_dir)
    try:
        return await service.create_backup()
    except BackupError as err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err)) from err


@router.get("/backups")
async def list_backups(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> list[dict[str, Any]]:
    """List available database backups."""
    db = request.app.state.database
    settings = request.app.state.settings
    backup_dir = Path(settings.backup_directory)

    service = BackupService(db, backup_dir)
    return await service.list_backups()


@router.post("/backups/restore")
async def restore_backup(
    request: Request,
    body: RestoreRequest,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, Any]:
    """Restore SQLite database and ChromaDB state from a safe backup bundle."""
    db = request.app.state.database
    settings = request.app.state.settings
    backup_dir = Path(settings.backup_directory)
    chroma_dir = Path(settings.memory_chroma_directory) if settings.memory_semantic_provider == "chromadb" else None

    archive_path = backup_dir / f"{body.backup_id}.tar.gz"
    if not archive_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup archive not found")

    service = BackupService(db, backup_dir, chroma_dir)
    try:
        return await service.restore_backup(archive_path)
    except BackupError as err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err)) from err


@router.get("/diagnostics")
async def get_diagnostics(
    request: Request,
    _context: Annotated[AuthenticatedOwnerContext, Depends(authenticated_context)],
) -> dict[str, Any]:
    """Get redacted deployment operational diagnostics report."""
    service = DiagnosticsService(request.app)
    return await service.generate_report()
