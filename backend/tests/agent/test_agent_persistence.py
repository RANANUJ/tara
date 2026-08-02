from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tara_api.domain.agent import AgentInputSource, AgentRequest, AgentResponse, AgentState, ModelUsage
from tara_api.persistence.agent_store import SqlAlchemyAgentPersistenceStore
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore
from tara_api.persistence.database import Database


async def test_agent_store_persists_successful_turns_atomically(database: Database) -> None:
    auth = SqlAlchemyAuthenticationStore(database)
    owner = await auth.bootstrap("owner@example.test", "not-a-token")
    assert owner is not None
    session = await auth.create(owner.id, "safe-hash", datetime.now(UTC) + timedelta(hours=1), None)
    store = SqlAlchemyAgentPersistenceStore(database)
    conversation_id = await store.resolve_conversation(owner.id, None)
    request = AgentRequest(uuid4(), uuid4(), owner.id, session.id, None, AgentInputSource.DIRECT_TEXT, "user text", datetime.now(UTC), conversation_id, None, "idempotency")

    assert await store.record_accepted(request) is True
    response = AgentResponse(request.request_id, "assistant text", AgentState.COMPLETED, datetime.now(UTC))
    await store.record_completed(request, response, provider_name="fake", model_identifier="fake-local", usage=ModelUsage(3, 2), duration_ms=7)

    async with database.unit_of_work() as unit_of_work:
        turns = await unit_of_work.turns.list_for_conversation(conversation_id)
        record = await unit_of_work.agent_requests.get_by_idempotency(owner.id, session.id, "idempotency")
    assert [turn.content for turn in turns] == ["user text", "assistant text"]
    assert record is not None and record.status == AgentState.COMPLETED.value
    assert record.usage == {"input_tokens": 3, "output_tokens": 2}
    assert "prompt" not in str(turns[0].safe_metadata).lower()
