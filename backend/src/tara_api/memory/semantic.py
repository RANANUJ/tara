"""Offline, rebuildable semantic-index adapters for authoritative SQLite memory."""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from tara_api.persistence.types import StructuredMemoryRecord


@dataclass(frozen=True, slots=True)
class SemanticMatch:
    memory_id: UUID
    score: float


class SemanticIndexUnavailableError(RuntimeError):
    """Raised when derived semantic search cannot safely run."""


class SemanticMemoryIndex(Protocol):
    async def upsert(self, records: Sequence[StructuredMemoryRecord]) -> None: ...

    async def delete(self, memory_ids: Sequence[UUID]) -> None: ...

    async def search(self, query: str, limit: int) -> tuple[SemanticMatch, ...]: ...

    async def clear(self) -> None: ...


class UnavailableSemanticMemoryIndex:
    """Explicit disabled adapter that preserves structured-memory availability."""

    async def upsert(self, records: Sequence[StructuredMemoryRecord]) -> None:
        raise SemanticIndexUnavailableError("semantic indexing is disabled")

    async def delete(self, memory_ids: Sequence[UUID]) -> None:
        raise SemanticIndexUnavailableError("semantic indexing is disabled")

    async def search(self, query: str, limit: int) -> tuple[SemanticMatch, ...]:
        raise SemanticIndexUnavailableError("semantic indexing is disabled")

    async def clear(self) -> None:
        raise SemanticIndexUnavailableError("semantic indexing is disabled")


class InMemorySemanticMemoryIndex:
    """Deterministic process-local index used by tests and unavailable-index fallback tests."""

    def __init__(self) -> None:
        self._records: dict[UUID, StructuredMemoryRecord] = {}

    async def upsert(self, records: Sequence[StructuredMemoryRecord]) -> None:
        self._records.update({record.id: record for record in records})

    async def delete(self, memory_ids: Sequence[UUID]) -> None:
        for memory_id in memory_ids:
            self._records.pop(memory_id, None)

    async def search(self, query: str, limit: int) -> tuple[SemanticMatch, ...]:
        query_vector = _embedding(query)
        matches = [SemanticMatch(memory_id, _cosine(query_vector, _embedding(record.content))) for memory_id, record in self._records.items()]
        return tuple(sorted(matches, key=lambda match: (-match.score, str(match.memory_id)))[:limit])

    async def clear(self) -> None:
        self._records.clear()


class ChromaSemanticMemoryIndex:
    """Chroma adapter with caller-supplied deterministic vectors and no model downloads."""

    def __init__(self, directory: Path, collection_name: str = "tara_structured_memories") -> None:
        self._directory = directory
        self._collection_name = collection_name
        self._collection: Any | None = None
        self._lock = asyncio.Lock()

    async def upsert(self, records: Sequence[StructuredMemoryRecord]) -> None:
        if not records:
            return
        collection = await self._get_collection()
        await asyncio.to_thread(
            collection.upsert,
            ids=[str(record.id) for record in records],
            embeddings=[_embedding(record.content) for record in records],
            documents=[record.content for record in records],
            metadatas=[{"category": record.category.value, "pinned": record.pinned} for record in records],
        )

    async def delete(self, memory_ids: Sequence[UUID]) -> None:
        if not memory_ids:
            return
        collection = await self._get_collection()
        await asyncio.to_thread(collection.delete, ids=[str(memory_id) for memory_id in memory_ids])

    async def search(self, query: str, limit: int) -> tuple[SemanticMatch, ...]:
        if not query.strip() or limit < 1:
            return ()
        collection = await self._get_collection()
        response = await asyncio.to_thread(
            collection.query,
            query_embeddings=[_embedding(query)],
            n_results=limit,
            include=["distances"],
        )
        identifiers = response.get("ids", [[]])[0]
        distances = response.get("distances", [[]])[0]
        if not isinstance(identifiers, list) or not isinstance(distances, list):
            raise SemanticIndexUnavailableError("semantic index returned an invalid response")
        matches: list[SemanticMatch] = []
        for identifier, distance in zip(identifiers, distances, strict=True):
            try:
                memory_id = UUID(str(identifier))
                score = max(0.0, min(1.0, 1.0 - float(distance)))
            except (TypeError, ValueError):
                continue
            matches.append(SemanticMatch(memory_id, score))
        return tuple(matches)

    async def clear(self) -> None:
        collection = await self._get_collection()
        await asyncio.to_thread(collection.delete, where={})

    async def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        async with self._lock:
            if self._collection is not None:
                return self._collection
            self._directory.mkdir(parents=True, exist_ok=True)
            self._collection = await asyncio.to_thread(self._create_collection)
            return self._collection

    def _create_collection(self) -> Any:
        try:
            import chromadb
        except ImportError as error:
            raise SemanticIndexUnavailableError("semantic index dependency is unavailable") from error
        try:
            client = chromadb.PersistentClient(path=str(self._directory))
            return client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as error:  # Chroma exceptions deliberately remain internal.
            raise SemanticIndexUnavailableError("semantic index is unavailable") from error


def _embedding(text: str, dimensions: int = 64) -> list[float]:
    values = [0.0] * dimensions
    for token in text.casefold().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        values[int.from_bytes(digest[:2], "big") % dimensions] += 1.0
    magnitude = math.sqrt(sum(value * value for value in values))
    return [value / magnitude for value in values] if magnitude else values


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
