from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from tara_api.agent.prompt import DefaultPromptBuilder
from tara_api.agent.registry import AgentRequestRegistry
from tara_api.agent.routing import DeterministicIntentRouter
from tara_api.agent.service import AgentService
from tara_api.domain.agent import AgentRequest, AgentResponse, AgentState, ContextRequest, ModelFinishReason, ModelRequest, ModelResponse, ModelUsage, ProviderHealthState, StructuredContext
from tara_api.domain.auth import AuthenticatedOwnerContext, Owner, OwnerSession


class ActiveSessions:
    def __init__(self) -> None:
        self.active: set[tuple[UUID, UUID]] = set()

    async def is_owner_session_active(self, owner_id: UUID, session_id: UUID) -> bool:
        return (owner_id, session_id) in self.active


class EmptyContext:
    async def get_context(self, _request: ContextRequest) -> StructuredContext:
        return StructuredContext((), 0)


class MemoryAgentStore:
    def __init__(self) -> None:
        self.accepted: set[UUID] = set()
        self.completed: list[tuple[AgentRequest, AgentResponse, str | None, str | None, ModelUsage | None, int | None]] = []
        self.terminals: list[tuple[AgentRequest, AgentState, object]] = []
        self.conversations: dict[UUID, UUID] = {}

    async def resolve_conversation(self, owner_id: UUID, conversation_id: UUID | None) -> UUID:
        if conversation_id is None:
            conversation_id = uuid4()
            self.conversations[conversation_id] = owner_id
        if self.conversations.get(conversation_id) != owner_id:
            raise RuntimeError
        return conversation_id

    async def record_accepted(self, request: AgentRequest) -> bool:
        if request.request_id in self.accepted:
            return False
        self.accepted.add(request.request_id)
        return True

    async def record_completed(self, request: AgentRequest, response: AgentResponse, *, provider_name: str | None, model_identifier: str | None, usage: ModelUsage | None, duration_ms: int | None) -> None:
        self.completed.append((request, response, provider_name, model_identifier, usage, duration_ms))

    async def record_terminal(self, request: AgentRequest, state: AgentState, error: object) -> None:
        self.terminals.append((request, state, error))


def owner_context(owner_id: UUID | None = None, session_id: UUID | None = None) -> AuthenticatedOwnerContext:
    now = datetime.now(UTC)
    owner = Owner(owner_id or uuid4(), "owner@example.test", now)
    return AuthenticatedOwnerContext(owner, OwnerSession(session_id or uuid4(), owner.id, now, now.replace(year=now.year + 1), now, None, None))


def registry(**overrides: int) -> AgentRequestRegistry:
    values = {"maximum_queued": 8, "maximum_concurrent": 1, "maximum_per_connection": 2, "maximum_per_session": 4, "maximum_per_owner": 8, "maximum_terminal_records": 8}
    values.update(overrides)
    from datetime import timedelta

    return AgentRequestRegistry(**values, terminal_retention=timedelta(minutes=5))


@pytest.fixture
def active_sessions() -> ActiveSessions:
    return ActiveSessions()


@pytest.fixture
def memory_store() -> MemoryAgentStore:
    return MemoryAgentStore()


def service(active_sessions: ActiveSessions, memory_store: MemoryAgentStore, provider, **limits):  # type: ignore[no-untyped-def]
    model_selector = limits.pop("model_selector", None)
    tool_loop = limits.pop("tool_loop", None)
    return AgentService(
        registry=registry(**limits),
        persistence=memory_store,
        session_validator=active_sessions,
        router=DeterministicIntentRouter(0.75),
        context_provider=lambda _owner_id: EmptyContext(),
        prompt_builder=DefaultPromptBuilder(),
        model_provider=provider,
        context_token_budget=1024,
        output_token_budget=64,
        timeout_seconds=1,
        model_selector=model_selector,
        tool_loop=tool_loop,
    )


class CountingProvider:
    name = "counting"
    model_identifier = "counting-model"
    streaming_supported = False

    def __init__(self, *, delay_seconds: float = 0, failure: Exception | None = None) -> None:
        self.calls = 0
        self.delay_seconds = delay_seconds
        self.failure = failure

    async def generate(self, _request: ModelRequest) -> ModelResponse:
        import asyncio

        self.calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.failure is not None:
            raise self.failure
        return ModelResponse("provider response", self.model_identifier, ModelFinishReason.STOP, 1, ModelUsage(1, 2))

    async def readiness(self):  # type: ignore[no-untyped-def]
        from tara_api.domain.agent import ModelReadiness

        return ModelReadiness(True, ProviderHealthState.READY)
