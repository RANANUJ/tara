"""Deterministic two-tier local-model selection for the bounded agent loop."""

from tara_api.domain.agent import (
    IntentCategory,
    IntentReasonCode,
    IntentRoute,
    LanguageModelProvider,
    ModelSelection,
    ModelTier,
    ModelTierReasonCode,
)


class DeterministicModelProviderSelector:
    """Choose a configured provider from server-owned route metadata only."""

    def __init__(self, fast: LanguageModelProvider, reasoning: LanguageModelProvider) -> None:
        self._fast = fast
        self._reasoning = reasoning

    def select(self, route: IntentRoute, _text: str) -> ModelSelection:
        if route.category is IntentCategory.MEMORY_QUERY:
            return ModelSelection(ModelTier.REASONING, ModelTierReasonCode.REASONING_MEMORY, self._reasoning)
        if route.reason_code is IntentReasonCode.QUESTION and self._is_complex_question(_text):
            return ModelSelection(ModelTier.REASONING, ModelTierReasonCode.REASONING_COMPLEX_QUESTION, self._reasoning)
        if route.category is IntentCategory.SAFE_READ_ONLY_REQUEST:
            return ModelSelection(ModelTier.FAST, ModelTierReasonCode.FAST_READ_ONLY, self._fast)
        if route.category is IntentCategory.FACTUAL_QUESTION:
            return ModelSelection(ModelTier.FAST, ModelTierReasonCode.FAST_FACTUAL, self._fast)
        return ModelSelection(ModelTier.FAST, ModelTierReasonCode.FAST_CONVERSATION, self._fast)

    @staticmethod
    def _is_complex_question(text: str) -> bool:
        normalized = text.casefold()
        return any(marker in normalized for marker in ("compare", "analyse", "analyze", "step by step", "tradeoff", "plan "))
