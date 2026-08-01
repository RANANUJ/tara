from uuid import uuid4

import pytest

from tara_api.agent.prompt import DefaultPromptBuilder
from tara_api.domain.agent import ContextItem, ContextSensitivity, ContextSourceKind, ContextSourceMetadata, StructuredContext


def item(text: str, *, pinned: bool = False) -> ContextItem:
    return ContextItem(
        text,
        ContextSensitivity.NORMAL,
        ContextSourceMetadata(ContextSourceKind.STRUCTURED_MEMORY, uuid4(), category="preference", pinned=pinned),
    )


def test_prompt_builder_uses_persona_safety_untrusted_context_and_user_message() -> None:
    result = DefaultPromptBuilder().build("Please help me", StructuredContext((item("Tea preference", pinned=True),), 4), model_context_token_budget=256)

    assert [message.role.value for message in result.messages] == ["system", "system", "user", "user"]
    assert "Tara" in result.messages[0].text
    assert "untrusted reference" in result.messages[1].text
    assert "[UNTRUSTED_CONTEXT" in result.messages[2].text
    assert result.messages[-1].text == "Please help me"
    assert "tool" not in " ".join(message.text for message in result.messages).lower()
    assert "chain of thought" not in " ".join(message.text for message in result.messages).lower()


def test_prompt_builder_keeps_context_bounded_and_truncates_deterministically() -> None:
    context = StructuredContext((item("a" * 30), item("b" * 30)), 15)

    result = DefaultPromptBuilder().build("hello", context, model_context_token_budget=120)

    assert result.context_items_included == 1
    assert result.context_truncated is True
    assert result.estimated_tokens <= 120
    assert "a" * 30 in result.messages[2].text


def test_prompt_builder_rejects_user_input_that_cannot_fit_system_policy() -> None:
    with pytest.raises(ValueError, match="prompt budget"):
        DefaultPromptBuilder().build("x" * 400, StructuredContext((), 0), model_context_token_budget=20)
