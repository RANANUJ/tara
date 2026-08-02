"""APScheduler-compatible memory retention and consolidation jobs."""

from __future__ import annotations

from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from tara_api.memory.service import MemoryService
from tara_api.persistence.types import MemoryCategory, MemorySource


@dataclass(frozen=True, slots=True)
class MemoryLifecycleReport:
    expired_deleted: int
    duplicate_facts_skipped: int


class MemoryLifecycleService:
    """Runs bounded retention cleanup and safe duplicate-fact consolidation."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory_service = memory_service

    async def run_retention(self) -> int:
        deleted = await self._memory_service.delete_expired()
        await self._memory_service.sync_index()
        return deleted

    async def consolidate(self) -> int:
        records = await self._memory_service.browse(limit=1000)
        seen: set[str] = set()
        duplicates = 0
        for record in records:
            if record.category != MemoryCategory.FACT or record.source != MemorySource.CONSOLIDATION:
                continue
            fingerprint = " ".join(record.content.casefold().split())
            if fingerprint in seen:
                await self._memory_service.hard_delete(record.id, confirmed=True)
                duplicates += 1
            else:
                seen.add(fingerprint)
        if duplicates:
            await self._memory_service.sync_index()
        return duplicates

    async def run_all(self) -> MemoryLifecycleReport:
        return MemoryLifecycleReport(await self.run_retention(), await self.consolidate())


class MemoryLifecycleScheduler:
    """Own APScheduler jobs without persisting application payloads in scheduler state."""

    def __init__(self, lifecycle: MemoryLifecycleService) -> None:
        self._lifecycle = lifecycle
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self._scheduler.add_job(self._lifecycle.run_retention, "interval", hours=1, id="memory-retention", replace_existing=True)
        self._scheduler.add_job(self._lifecycle.consolidate, "interval", hours=24, id="memory-consolidation", replace_existing=True)
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
