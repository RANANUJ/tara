"""M11/M12 authoritative-memory, semantic-index, and lifecycle coverage."""

from datetime import UTC, datetime, timedelta

import pytest

from tara_api.memory.exports import MemoryExportService
from tara_api.memory.lifecycle import MemoryLifecycleService
from tara_api.memory.semantic import InMemorySemanticMemoryIndex, UnavailableSemanticMemoryIndex
from tara_api.memory.service import MemoryService
from tara_api.persistence.database import Database
from tara_api.persistence.types import MemoryCategory, MemorySource, RetentionCategory, utc_now


async def test_structured_memory_remains_available_when_semantic_index_is_unavailable(database: Database) -> None:
    service = MemoryService(database, UnavailableSemanticMemoryIndex(), now=utc_now)

    record = await service.create(
        category=MemoryCategory.PREFERENCE,
        content="Use concise replies",
        source=MemorySource.USER,
        retention_category=RetentionCategory.PREFERENCE,
    )

    assert (await service.browse())[0].id == record.id
    assert (await service.search("concise"))[0].record.id == record.id
    assert (await service.sync_index()).unavailable is True


async def test_outbox_sync_and_rebuild_only_return_current_sqlite_records(database: Database) -> None:
    index = InMemorySemanticMemoryIndex()
    service = MemoryService(database, index, now=utc_now)
    record = await service.create(
        category=MemoryCategory.FACT,
        content="The project uses SQLite locally",
        source=MemorySource.USER,
        retention_category=RetentionCategory.PREFERENCE,
    )

    assert (await service.sync_index()).processed == 1
    assert (await service.search("SQLite"))[0].record.id == record.id
    assert await service.hard_delete(record.id, confirmed=True) is True
    assert (await service.sync_index()).processed == 1
    assert await service.search("SQLite") == ()
    assert await service.rebuild_index() == 0


async def test_retention_preserves_pinned_memories_and_export_is_serializable(database: Database) -> None:
    index = InMemorySemanticMemoryIndex()
    service = MemoryService(database, index, now=utc_now)
    expired = await service.create(
        category=MemoryCategory.FACT,
        content="An expired casual memory",
        source=MemorySource.CONVERSATION,
        retention_category=RetentionCategory.CASUAL,
        expires_at=utc_now() - timedelta(seconds=1),
    )
    pinned = await service.create(
        category=MemoryCategory.FACT,
        content="A pinned casual memory",
        source=MemorySource.CONVERSATION,
        retention_category=RetentionCategory.CASUAL,
        pinned=True,
        expires_at=utc_now() - timedelta(seconds=1),
    )

    lifecycle = MemoryLifecycleService(service)
    assert await lifecycle.run_retention() == 1
    exported = await service.export()
    assert {entry["id"] for entry in exported} == {str(pinned.id)}
    assert expired.id not in {record.id for record in await service.browse()}


async def test_memory_hard_delete_requires_confirmation(database: Database) -> None:
    service = MemoryService(database, InMemorySemanticMemoryIndex(), now=utc_now)
    record = await service.create(
        category=MemoryCategory.TASK,
        content="Remove me only after confirmation",
        source=MemorySource.USER,
        retention_category=RetentionCategory.TASK,
    )

    with pytest.raises(PermissionError):
        await service.hard_delete(record.id, confirmed=False)
    assert (await service.browse())[0].id == record.id


async def test_confirmed_export_expires_and_is_scrubbed_after_hard_delete(database: Database) -> None:
    clock = [datetime(2026, 8, 2, tzinfo=UTC)]
    service = MemoryService(database, InMemorySemanticMemoryIndex(), now=lambda: clock[0])
    record = await service.create(
        category=MemoryCategory.FACT,
        content="Synthetic export record",
        source=MemorySource.USER,
        retention_category=RetentionCategory.PREFERENCE,
    )
    exports = MemoryExportService(service, now=lambda: clock[0], ttl=timedelta(seconds=1))

    artifact = await exports.create(confirmed=True)
    assert exports.get(artifact.id) is not None
    exports.remove_memory(record.id)
    scrubbed = exports.get(artifact.id)
    assert scrubbed is not None
    assert scrubbed.records == ()
    clock[0] += timedelta(seconds=2)
    assert exports.get(artifact.id) is None
