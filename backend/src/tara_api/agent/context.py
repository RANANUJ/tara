"""Persisted-only, owner-bound structured context selection for M9B."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import UUID

from tara_api.agent.context_policy import ContextSensitivityPolicy
from tara_api.domain.agent import (
    ContextBudget,
    ContextItem,
    ContextRequest,
    ContextSensitivity,
    ContextSourceKind,
    ContextSourceMetadata,
    ModelRole,
    StructuredContext,
)
from tara_api.persistence.database import Database
from tara_api.persistence.repositories.interfaces import ConversationTurnRepository, StructuredMemoryRepository
from tara_api.persistence.types import ConversationTurnRecord, ConversationTurnRole, StructuredMemoryRecord


class ContextAccessDeniedError(PermissionError):
    """Raised when server-side owner identity does not match this context scope."""


class PersistenceStructuredContextProvider:
    """Select pinned memories and completed recent turns without semantic retrieval."""

    def __init__(
        self,
        memories: StructuredMemoryRepository,
        turns: ConversationTurnRepository,
        *,
        owner_id: UUID,
        budget: ContextBudget,
        policy: ContextSensitivityPolicy,
        now: Callable[[], datetime],
        memory_sensitivity: Callable[[StructuredMemoryRecord], ContextSensitivity] | None = None,
        turn_sensitivity: Callable[[ConversationTurnRecord], ContextSensitivity] | None = None,
    ) -> None:
        self._memories = memories
        self._turns = turns
        self._owner_id = owner_id
        self._budget = budget
        self._policy = policy
        self._now = now
        self._memory_sensitivity = memory_sensitivity or (lambda _record: ContextSensitivity.NORMAL)
        self._turn_sensitivity = turn_sensitivity or (lambda _record: ContextSensitivity.NORMAL)

    async def get_context(self, request: ContextRequest) -> StructuredContext:
        if request.owner_id != self._owner_id:
            raise ContextAccessDeniedError("context is not available")
        now = self._utc_now()
        memory_records = await self._memories.list_for_context(now, limit=self._budget.memory_limit)
        memory_items = self._memory_items(memory_records)
        turn_items: tuple[ContextItem, ...] = ()
        if request.conversation_id is not None:
            recent_records = await self._turns.list_completed_for_conversation(
                request.conversation_id,
                limit=self._budget.recent_turn_limit,
            )
            turn_items = self._turn_items(reversed(recent_records))
        selected, truncated = self._apply_total_budget((*memory_items, *turn_items))
        return StructuredContext(selected, self._estimate_tokens(selected), truncated)

    def _memory_items(self, records: list[StructuredMemoryRecord]) -> tuple[ContextItem, ...]:
        candidates: list[ContextItem] = []
        for record in records:
            sensitivity = self._memory_sensitivity(record)
            if not self._policy.allows(sensitivity):
                continue
            candidates.append(
                self._item(
                    record.content,
                    sensitivity,
                    ContextSourceMetadata(
                        kind=ContextSourceKind.STRUCTURED_MEMORY,
                        record_id=record.id,
                        category=record.category.value,
                        pinned=record.pinned,
                    ),
                    self._budget.memory_item_char_limit,
                )
            )
        return tuple(candidates)

    def _turn_items(self, records: Iterable[ConversationTurnRecord]) -> tuple[ContextItem, ...]:
        candidates: list[ContextItem] = []
        for record in records:
            sensitivity = self._turn_sensitivity(record)
            if not self._policy.allows(sensitivity):
                continue
            role = ModelRole.USER if record.role == ConversationTurnRole.USER else ModelRole.ASSISTANT
            candidates.append(
                self._item(
                    record.content,
                    sensitivity,
                    ContextSourceMetadata(
                        kind=ContextSourceKind.CONVERSATION_TURN,
                        record_id=record.id,
                        category="conversation_turn",
                        role=role,
                        sequence=record.sequence,
                    ),
                    self._budget.recent_turn_char_limit,
                )
            )
        return tuple(candidates)

    @staticmethod
    def _item(text: str, sensitivity: ContextSensitivity, source: ContextSourceMetadata, limit: int) -> ContextItem:
        normalized = " ".join(text.split())
        if not normalized:
            raise ValueError("persisted context cannot be blank")
        return ContextItem(normalized[:limit], sensitivity, source, truncated=len(normalized) > limit)

    def _apply_total_budget(self, items: tuple[ContextItem, ...]) -> tuple[tuple[ContextItem, ...], bool]:
        selected: list[ContextItem] = []
        used_chars = 0
        truncated = False
        for item in items:
            remaining = self._budget.total_char_limit - used_chars
            if remaining <= 0:
                truncated = True
                break
            if len(item.text) > remaining:
                selected.append(ContextItem(item.text[:remaining], item.sensitivity, item.source, truncated=True))
                truncated = True
                break
            selected.append(item)
            used_chars += len(item.text)
            truncated = truncated or item.truncated
        return tuple(selected), truncated

    @staticmethod
    def _estimate_tokens(items: tuple[ContextItem, ...]) -> int:
        total_chars = sum(len(item.text) for item in items)
        return (total_chars + 3) // 4

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("context clock must return an aware UTC timestamp")
        return value.astimezone(UTC)


class DatabaseStructuredContextProvider:
    """Open a short-lived unit of work for one owner-bound context read."""

    def __init__(
        self,
        database: Database,
        *,
        owner_id: UUID,
        budget: ContextBudget,
        policy: ContextSensitivityPolicy,
        now: Callable[[], datetime],
    ) -> None:
        self._database = database
        self._owner_id = owner_id
        self._budget = budget
        self._policy = policy
        self._now = now

    async def get_context(self, request: ContextRequest) -> StructuredContext:
        async with self._database.unit_of_work() as unit_of_work:
            provider = PersistenceStructuredContextProvider(
                unit_of_work.memories,
                unit_of_work.turns,
                owner_id=self._owner_id,
                budget=self._budget,
                policy=self._policy,
                now=self._now,
            )
            return await provider.get_context(request)
