"""Short-lived in-process memory-export artifacts with no secret fields."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from tara_api.memory.service import MemoryService


@dataclass(frozen=True, slots=True)
class MemoryExportArtifact:
    id: UUID
    records: tuple[dict[str, str | bool | None], ...]
    expires_at: datetime


class MemoryExportService:
    """Stages expiring exports in memory only; callers must enforce confirmation first."""

    def __init__(self, memory_service: MemoryService, *, now: Callable[[], datetime], ttl: timedelta = timedelta(minutes=15)) -> None:
        self._memory_service = memory_service
        self._now = now
        self._ttl = ttl
        self._artifacts: dict[UUID, MemoryExportArtifact] = {}

    async def create(self, *, confirmed: bool) -> MemoryExportArtifact:
        if not confirmed:
            raise PermissionError("memory export requires explicit confirmation")
        now = self._utc_now()
        artifact = MemoryExportArtifact(uuid4(), await self._memory_service.export(), now + self._ttl)
        self._artifacts[artifact.id] = artifact
        return artifact

    def get(self, export_id: UUID) -> MemoryExportArtifact | None:
        self.remove_expired()
        return self._artifacts.get(export_id)

    def delete(self, export_id: UUID) -> bool:
        return self._artifacts.pop(export_id, None) is not None

    def remove_memory(self, memory_id: UUID) -> None:
        identity = str(memory_id)
        for export_id, artifact in tuple(self._artifacts.items()):
            records = tuple(record for record in artifact.records if record["id"] != identity)
            self._artifacts[export_id] = MemoryExportArtifact(artifact.id, records, artifact.expires_at)

    def remove_expired(self) -> int:
        now = self._utc_now()
        expired_ids = [export_id for export_id, artifact in self._artifacts.items() if artifact.expires_at <= now]
        for export_id in expired_ids:
            del self._artifacts[export_id]
        return len(expired_ids)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("export clock must return an aware UTC timestamp")
        return value.astimezone(UTC)
