"""Owner-safe structured-memory operations with a transactional semantic-index outbox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from tara_api.memory.semantic import SemanticIndexUnavailableError, SemanticMemoryIndex
from tara_api.persistence.database import Database
from tara_api.persistence.types import (
    MemoryCategory,
    MemoryIndexOperation,
    MemorySource,
    MemoryTaskStatus,
    RetentionCategory,
    StructuredMemoryRecord,
)


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    record: StructuredMemoryRecord
    score: float


@dataclass(frozen=True, slots=True)
class IndexSyncReport:
    processed: int
    unavailable: bool


class MemoryService:
    """Keep SQLite authoritative and use Chroma only as a best-effort derived index."""

    def __init__(
        self,
        database: Database,
        semantic_index: SemanticMemoryIndex,
        *,
        now: Callable[[], datetime],
        casual_retention: timedelta = timedelta(days=30),
    ) -> None:
        self._database = database
        self._semantic_index = semantic_index
        self._now = now
        self._casual_retention = casual_retention

    async def create(
        self,
        *,
        category: MemoryCategory,
        content: str,
        source: MemorySource,
        retention_category: RetentionCategory,
        source_reference: str | None = None,
        pinned: bool = False,
        expires_at: datetime | None = None,
        task_status: MemoryTaskStatus | None = None,
    ) -> StructuredMemoryRecord:
        normalized_content = " ".join(content.split())
        if not normalized_content:
            raise ValueError("memory content must not be blank")
        expiry = self._expiry(retention_category, pinned, expires_at)
        async with self._database.unit_of_work() as unit_of_work:
            record = await unit_of_work.memories.create(
                category,
                normalized_content,
                source,
                retention_category,
                source_reference=source_reference,
                pinned=pinned,
                expires_at=expiry,
                task_status=task_status,
            )
            await unit_of_work.memory_index_outbox.enqueue(record.id, MemoryIndexOperation.UPSERT)
            return record

    async def update(
        self,
        memory_id: UUID,
        *,
        content: str | None = None,
        pinned: bool | None = None,
        task_status: MemoryTaskStatus | None = None,
    ) -> StructuredMemoryRecord | None:
        normalized_content = " ".join(content.split()) if content is not None else None
        if normalized_content == "":
            raise ValueError("memory content must not be blank")
        async with self._database.unit_of_work() as unit_of_work:
            record = await unit_of_work.memories.update(memory_id, content=normalized_content, pinned=pinned, task_status=task_status)
            if record is not None:
                await unit_of_work.memory_index_outbox.enqueue(record.id, MemoryIndexOperation.UPSERT)
            return record

    async def browse(self, limit: int = 50, offset: int = 0) -> tuple[StructuredMemoryRecord, ...]:
        async with self._database.unit_of_work() as unit_of_work:
            return tuple(await unit_of_work.memories.list_for_context(self._utc_now(), limit=limit, offset=offset))

    async def search(self, query: str, limit: int = 10) -> tuple[MemorySearchResult, ...]:
        if not query.strip() or limit < 1:
            return ()
        try:
            matches = await self._semantic_index.search(query, limit)
        except SemanticIndexUnavailableError:
            return await self._lexical_search(query, limit)
        current_records = {record.id: record for record in await self.browse(limit=500)}
        results = [MemorySearchResult(current_records[match.memory_id], match.score) for match in matches if match.memory_id in current_records]
        return tuple(results)

    async def hard_delete(self, memory_id: UUID, *, confirmed: bool) -> bool:
        if not confirmed:
            raise PermissionError("memory deletion requires explicit confirmation")
        return await self._delete_authoritative(memory_id)

    async def delete_expired(self, limit: int = 100) -> int:
        async with self._database.unit_of_work() as unit_of_work:
            records = await unit_of_work.memories.list_for_retention_cleanup(self._utc_now(), limit=limit)
            for record in records:
                await unit_of_work.memories.hard_delete(record.id)
                await unit_of_work.memory_index_outbox.enqueue(record.id, MemoryIndexOperation.DELETE)
            return len(records)

    async def export(self) -> tuple[dict[str, str | bool | None], ...]:
        async with self._database.unit_of_work() as unit_of_work:
            records = await unit_of_work.memories.list_for_export(limit=1000)
            return tuple(record.to_export_dict() for record in records)

    async def sync_index(self, limit: int = 100) -> IndexSyncReport:
        async with self._database.unit_of_work() as unit_of_work:
            entries = await unit_of_work.memory_index_outbox.list_pending(limit=limit)
            for entry in entries:
                if entry.operation == MemoryIndexOperation.DELETE:
                    try:
                        await self._semantic_index.delete((entry.memory_id,))
                    except SemanticIndexUnavailableError:
                        return IndexSyncReport(0, unavailable=True)
                else:
                    record = await unit_of_work.memories.get_by_id(entry.memory_id)
                    if record is None:
                        try:
                            await self._semantic_index.delete((entry.memory_id,))
                        except SemanticIndexUnavailableError:
                            return IndexSyncReport(0, unavailable=True)
                    else:
                        try:
                            await self._semantic_index.upsert((record,))
                        except SemanticIndexUnavailableError:
                            return IndexSyncReport(0, unavailable=True)
                await unit_of_work.memory_index_outbox.mark_processed(entry.id, self._utc_now())
            return IndexSyncReport(len(entries), unavailable=False)

    async def rebuild_index(self) -> int:
        records = await self.browse(limit=1000)
        try:
            await self._semantic_index.clear()
            await self._semantic_index.upsert(records)
        except SemanticIndexUnavailableError:
            return 0
        return len(records)

    async def _delete_authoritative(self, memory_id: UUID) -> bool:
        async with self._database.unit_of_work() as unit_of_work:
            deleted = await unit_of_work.memories.hard_delete(memory_id)
            if deleted:
                await unit_of_work.memory_index_outbox.enqueue(memory_id, MemoryIndexOperation.DELETE)
            return deleted

    async def _lexical_search(self, query: str, limit: int) -> tuple[MemorySearchResult, ...]:
        terms = set(query.casefold().split())
        results = []
        for record in await self.browse(limit=500):
            score = float(len(terms.intersection(record.content.casefold().split())))
            if score:
                results.append(MemorySearchResult(record, score))
        return tuple(sorted(results, key=lambda result: (-result.score, str(result.record.id)))[:limit])

    def _expiry(self, retention: RetentionCategory, pinned: bool, expires_at: datetime | None) -> datetime | None:
        if pinned or retention != RetentionCategory.CASUAL:
            return expires_at
        return self._utc_now() + self._casual_retention if expires_at is None else expires_at.astimezone(UTC)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("memory clock must return an aware UTC timestamp")
        return value.astimezone(UTC)
