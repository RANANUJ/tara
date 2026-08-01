from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.domain.agent import AgentInputSource, AgentRequest, AgentResponse, AgentSession, AgentState, IntentCategory, IntentClassification, ModelMessage, ModelRequest, ModelRole, ModelUsage


def test_agent_models_require_bounded_text_and_utc_timestamps() -> None:
    now = datetime.now(UTC)
    session = AgentSession(uuid4(), uuid4(), uuid4(), None, now)
    request = AgentRequest(uuid4(), session.agent_session_id, session.owner_id, session.session_id, None, AgentInputSource.DIRECT_TEXT, "hello", now)
    response = AgentResponse(request.request_id, "hello", AgentState.COMPLETED, now)
    model_request = ModelRequest(uuid4(), (ModelMessage(ModelRole.USER, "hello"),), 128, 32, now)

    assert request.connection_id is None
    assert response.state is AgentState.COMPLETED
    assert model_request.messages[0].role is ModelRole.USER
    assert not hasattr(request, "chain_of_thought")

    with pytest.raises(ValueError):
        AgentRequest(uuid4(), uuid4(), uuid4(), uuid4(), None, AgentInputSource.DIRECT_TEXT, "", now)
    with pytest.raises(ValueError):
        AgentRequest(uuid4(), uuid4(), uuid4(), uuid4(), None, AgentInputSource.DIRECT_TEXT, "x" * 12_001, now)
    with pytest.raises(ValueError):
        ModelRequest(uuid4(), (ModelMessage(ModelRole.USER, "hello"),), 128, 32, now.replace(tzinfo=None))


def test_agent_enums_usage_and_confidence_are_validated() -> None:
    assert IntentClassification(IntentCategory.CONVERSATION, 1).confidence == 1
    with pytest.raises(ValueError):
        IntentClassification(IntentCategory.CONVERSATION, 1.1)
    with pytest.raises(ValueError):
        ModelUsage(input_tokens=-1)
    with pytest.raises(ValueError):
        AgentState("invalid")
