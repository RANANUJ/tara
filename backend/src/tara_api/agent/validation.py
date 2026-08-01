"""Provider-neutral request and response validation."""

import unicodedata

from tara_api.domain.agent import (
    MAX_AGENT_INPUT_CHARS,
    MAX_MODEL_OUTPUT_CHARS,
    AgentError,
    ModelProviderFailure,
    ModelRequest,
    ModelResponse,
)


def _contains_unsafe_characters(text: str) -> bool:
    return any(unicodedata.category(character) == "Cc" and character not in "\n\t" for character in text) or any(0xD800 <= ord(character) <= 0xDFFF for character in text)


class DefaultModelRequestValidator:
    """Apply bounded, provider-neutral input rules before an HTTP request."""

    def validate(self, request: ModelRequest) -> None:
        combined_length = sum(len(message.text) for message in request.messages)
        if combined_length > MAX_AGENT_INPUT_CHARS:
            raise ModelProviderFailure(AgentError.REQUEST_TOO_LARGE, "The model request is too large.")
        if combined_length > request.context_token_budget * 4:
            raise ModelProviderFailure(AgentError.CONTEXT_LIMIT_EXCEEDED, "The model context is too large.")
        if any(_contains_unsafe_characters(message.text) for message in request.messages):
            raise ModelProviderFailure(AgentError.REQUEST_TOO_LARGE, "The model request is invalid.")


class DefaultModelResponseValidator:
    """Normalize safe text and reject malformed or excessive provider output."""

    def validate(self, response: ModelResponse) -> ModelResponse:
        normalized = response.text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized or _contains_unsafe_characters(normalized):
            raise ModelProviderFailure(AgentError.INVALID_PROVIDER_RESPONSE, "The model response is invalid.")
        if len(normalized) > MAX_MODEL_OUTPUT_CHARS:
            raise ModelProviderFailure(AgentError.RESPONSE_TOO_LARGE, "The model response is too large.")
        if normalized == response.text:
            return response
        return ModelResponse(normalized, response.model_identifier, response.finish_reason, response.duration_ms, response.usage)
