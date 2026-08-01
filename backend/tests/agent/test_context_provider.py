from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from tara_api.agent.context import ContextAccessDeniedError, PersistenceStructuredContextProvider
from tara_api.agent.context_policy import ContextSensitivityPolicy
from tara_api.domain.agent import ContextBudget, ContextRequest, ContextSensitivity, ContextSourceKind, ModelRole
from tara_api.persistence.database import Database
from tara_api.persistence.types import ConversationTurnRole, ConversationTurnStatus, MemoryCategory, MemorySource, RetentionCategory


def budget() -> ContextBudget:
    return ContextBudget(4, 4, 64, 64, 300, 75)


async def test_context_provider_returns_pinned_memories_then_completed_recent_turns(database: Database) -> None:
    owner_id = uuid4()
    now = datetime.now(UTC)
    async with database.unit_of_work() as unit_of_work:
        conversation = await unit_of_work.conversations.create()
        await unit_of_work.memories.create(MemoryCategory.PREFERENCE, "new normal memory", MemorySource.USER, RetentionCategory.PREFERENCE)
        pinned = await unit_of_work.memories.create(MemoryCategory.PREFERENCE, "pinned memory", MemorySource.USER, RetentionCategory.PREFERENCE, pinned=True, source_reference="never-prompt")
        await unit_of_work.memories.create(MemoryCategory.TASK, "expired memory", MemorySource.USER, RetentionCategory.TASK, expires_at=now - timedelta(seconds=1))
        await unit_of_work.turns.create(conversation.id, 1, ConversationTurnRole.USER, ConversationTurnStatus.COMPLETED, "first completed turn")
        await unit_of_work.turns.create(conversation.id, 2, ConversationTurnRole.ASSISTANT, ConversationTurnStatus.COMPLETED, "second completed turn")
        await unit_of_work.turns.create(conversation.id, 3, ConversationTurnRole.USER, ConversationTurnStatus.FAILED, "failed turn")
        provider = PersistenceStructuredContextProvider(unit_of_work.memories, unit_of_work.turns, owner_id=owner_id, budget=budget(), policy=ContextSensitivityPolicy((ContextSensitivity.NORMAL,)), now=lambda: now)

        context = await provider.get_context(ContextRequest(owner_id, conversation.id))

    assert context.items[0].source.kind is ContextSourceKind.STRUCTURED_MEMORY
    assert context.items[0].source.record_id == pinned.id
    assert "expired" not in " ".join(item.text for item in context.items)
    turns = [item for item in context.items if item.source.kind is ContextSourceKind.CONVERSATION_TURN]
    assert [item.source.sequence for item in turns] == [1, 2]
    assert [item.source.role for item in turns] == [ModelRole.USER, ModelRole.ASSISTANT]
    assert not hasattr(context.items[0].source, "source_reference")


async def test_context_provider_enforces_owner_scope_and_sensitivity_policy(database: Database) -> None:
    owner_id = uuid4()
    async with database.unit_of_work() as unit_of_work:
        memory = await unit_of_work.memories.create(MemoryCategory.FACT, "private fact", MemorySource.USER, RetentionCategory.PREFERENCE)
        provider = PersistenceStructuredContextProvider(
            unit_of_work.memories,
            unit_of_work.turns,
            owner_id=owner_id,
            budget=budget(),
            policy=ContextSensitivityPolicy((ContextSensitivity.NORMAL,)),
            now=lambda: datetime.now(UTC),
            memory_sensitivity=lambda record: ContextSensitivity.PRIVATE if record.id == memory.id else ContextSensitivity.NORMAL,
        )

        assert (await provider.get_context(ContextRequest(owner_id, None))).items == ()
        with pytest.raises(ContextAccessDeniedError):
            await provider.get_context(ContextRequest(uuid4(), None))


async def test_context_provider_applies_item_and_total_budgets(database: Database) -> None:
    owner_id = uuid4()
    async with database.unit_of_work() as unit_of_work:
        await unit_of_work.memories.create(MemoryCategory.FACT, "a" * 30, MemorySource.USER, RetentionCategory.PREFERENCE, pinned=True)
        await unit_of_work.memories.create(MemoryCategory.FACT, "b" * 30, MemorySource.USER, RetentionCategory.PREFERENCE)
        provider = PersistenceStructuredContextProvider(
            unit_of_work.memories,
            unit_of_work.turns,
            owner_id=owner_id,
            budget=ContextBudget(2, 2, 16, 16, 40, 10),
            policy=ContextSensitivityPolicy((ContextSensitivity.NORMAL,)),
            now=lambda: datetime.now(UTC),
        )

        context = await provider.get_context(ContextRequest(owner_id, None))

    assert len(context.items[0].text) == 16
    assert sum(len(item.text) for item in context.items) <= 40
    assert context.estimated_tokens <= 10
    assert context.truncated is True
