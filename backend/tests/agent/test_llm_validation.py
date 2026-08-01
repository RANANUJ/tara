from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tara_api.agent.validation import DefaultModelRequestValidator, DefaultModelResponseValidator
from tara_api.domain.agent import AgentError, ModelFinishReason, ModelMessage, ModelProviderFailure, ModelRequest, ModelResponse, ModelRole


def test_request_validator_enforces_context_and_control_characters() -> None:
    validator = DefaultModelRequestValidator()
    with pytest.raises(ModelProviderFailure) as context_error:
        validator.validate(ModelRequest(uuid4(), (ModelMessage(ModelRole.USER, "x" * 9),), 2, 1, datetime.now(UTC)))
    assert context_error.value.code is AgentError.CONTEXT_LIMIT_EXCEEDED

    with pytest.raises(ModelProviderFailure):
        validator.validate(ModelRequest(uuid4(), (ModelMessage(ModelRole.USER, "bad\x00"),), 128, 1, datetime.now(UTC)))


def test_response_validator_normalizes_and_rejects_unsafe_text() -> None:
    validator = DefaultModelResponseValidator()
    normalized = validator.validate(ModelResponse("line one\r\nline two", "model", ModelFinishReason.STOP, 1))
    assert normalized.text == "line one\nline two"

    with pytest.raises(ModelProviderFailure) as error:
        validator.validate(ModelResponse("bad\x00", "model", ModelFinishReason.STOP, 1))
    assert error.value.code is AgentError.INVALID_PROVIDER_RESPONSE
