"""Persistence behavior tests for the M2 foundational repositories."""

import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from tara_api.persistence.database import Database
from tara_api.persistence.types import (
    ConfirmationAlreadyConsumedError,
    ConfirmationDecision,
    ConfirmationExpiredError,
    ConversationTurnRole,
    ConversationTurnStatus,
    MemoryCategory,
    MemorySource,
    PermissionGrantState,
    RetentionCategory,
    UnsafeConfigurationKeyError,
    utc_now,
)


async def test_repositories_create_list_update_and_delete(database: Database) -> None:
    async with database.unit_of_work() as unit_of_work:
        conversation = await unit_of_work.conversations.create("Bootstrap test")
        turn = await unit_of_work.turns.create(
            conversation.id,
            sequence=1,
            role=ConversationTurnRole.USER,
            status=ConversationTurnStatus.COMPLETED,
            content="Hello",
        )
        permission = await unit_of_work.permissions.create(
            "filesystem.read",
            grant_state=PermissionGrantState.ENABLED,
            scope={"root": "workspace"},
        )
        audit_event = await unit_of_work.audit_events.create("persistence.test", "succeeded")
        job = await unit_of_work.scheduler_jobs.create("cleanup", "retention_cleanup", "UTC")
        configuration = await unit_of_work.service_configurations.upsert(
            "retention_policy", {"task_days": 30}
        )

        assert turn.conversation_id == conversation.id
        assert permission.grant_state == PermissionGrantState.ENABLED
        assert audit_event.event_type == "persistence.test"
        assert job.enabled is True
        assert configuration.value == {"task_days": 30}

    async with database.unit_of_work() as unit_of_work:
        assert await unit_of_work.conversations.get_by_id(conversation.id) == conversation
        assert [item.id for item in await unit_of_work.turns.list_for_conversation(conversation.id)] == [
            turn.id
        ]
        assert (await unit_of_work.conversations.update_label(conversation.id, "Updated")) is not None
        assert (await unit_of_work.scheduler_jobs.update_enabled(job.id, False)) is not None
        assert await unit_of_work.service_configurations.delete("retention_policy") is True
        assert await unit_of_work.permissions.delete(permission.id) is True
        assert await unit_of_work.turns.delete(turn.id) is True
        assert await unit_of_work.conversations.delete(conversation.id) is True


async def test_foreign_keys_and_failed_transactions_do_not_leave_partial_writes(database: Database) -> None:
    with pytest.raises(IntegrityError):
        async with database.unit_of_work() as unit_of_work:
            await unit_of_work.conversations.create("Rolled back")
            await unit_of_work.turns.create(
                uuid4(),
                sequence=1,
                role=ConversationTurnRole.USER,
                status=ConversationTurnStatus.COMPLETED,
                content="invalid foreign key",
            )

    async with database.unit_of_work() as unit_of_work:
        assert await unit_of_work.conversations.list() == []


async def test_confirmation_consumption_is_one_time_and_expiry_aware(database: Database) -> None:
    async with database.unit_of_work() as unit_of_work:
        confirmation = await unit_of_work.confirmations.create(
            "memory.delete",
            "Delete one memory",
            "safe-action-hash",
            expires_at=utc_now() + timedelta(minutes=5),
        )
        expired_confirmation = await unit_of_work.confirmations.create(
            "memory.delete",
            "Delete expired memory",
            "expired-action-hash",
            expires_at=utc_now() - timedelta(seconds=1),
        )

    async def consume_once() -> bool:
        try:
            async with database.unit_of_work() as unit_of_work:
                await unit_of_work.confirmations.consume(
                    confirmation.id,
                    ConfirmationDecision.APPROVED,
                )
        except ConfirmationAlreadyConsumedError:
            return False
        return True

    results = await asyncio.gather(consume_once(), consume_once())

    assert results.count(True) == 1
    assert results.count(False) == 1

    with pytest.raises(ConfirmationExpiredError):
        async with database.unit_of_work() as unit_of_work:
            await unit_of_work.confirmations.consume(
                expired_confirmation.id,
                ConfirmationDecision.APPROVED,
            )


async def test_memory_hard_delete_retention_and_export_queries(database: Database) -> None:
    now = utc_now()
    async with database.unit_of_work() as unit_of_work:
        removable = await unit_of_work.memories.create(
            MemoryCategory.FACT,
            "Remove me",
            MemorySource.USER,
            RetentionCategory.CASUAL,
            expires_at=now - timedelta(days=1),
        )
        pinned = await unit_of_work.memories.create(
            MemoryCategory.PREFERENCE,
            "Keep me",
            MemorySource.USER,
            RetentionCategory.CASUAL,
            pinned=True,
            expires_at=now - timedelta(days=1),
        )
        preference = await unit_of_work.memories.create(
            MemoryCategory.PREFERENCE,
            "Long lived",
            MemorySource.USER,
            RetentionCategory.PREFERENCE,
        )

        cleanup = await unit_of_work.memories.list_for_retention_cleanup(now)
        exported = await unit_of_work.memories.list_for_export()
        assert [item.id for item in cleanup] == [removable.id]
        assert {item.id for item in exported} == {removable.id, pinned.id, preference.id}
        assert json.loads(json.dumps(exported[0].to_export_dict()))["id"] == str(exported[0].id)
        assert await unit_of_work.memories.hard_delete(removable.id) is True

    async with database.unit_of_work() as unit_of_work:
        assert await unit_of_work.memories.get_by_id(removable.id) is None


async def test_service_configuration_rejects_secret_fields(database: Database) -> None:
    with pytest.raises(UnsafeConfigurationKeyError):
        async with database.unit_of_work() as unit_of_work:
            await unit_of_work.service_configurations.upsert(
                "ui_preferences",
                {"provider": {"api_key": "must-not-persist"}},
            )
