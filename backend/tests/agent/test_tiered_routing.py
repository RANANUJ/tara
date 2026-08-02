from tara_api.agent.fake import FakeLanguageModelProvider
from tara_api.agent.routing import DeterministicIntentRouter
from tara_api.agent.tiered import DeterministicModelProviderSelector
from tara_api.domain.agent import ModelTier, ModelTierReasonCode


def test_simple_fixture_intents_select_the_fast_model() -> None:
    fast = FakeLanguageModelProvider(model_identifier="fast", environment="test")
    reasoning = FakeLanguageModelProvider(model_identifier="reasoning", environment="test")
    selection = DeterministicModelProviderSelector(fast, reasoning).select(
        DeterministicIntentRouter(0.75).classify("What time is it?"),
        "What time is it?",
    )

    assert selection.tier is ModelTier.FAST
    assert selection.reason_code is ModelTierReasonCode.FAST_FACTUAL
    assert selection.provider is fast


def test_reasoning_fixtures_select_the_reasoning_model_with_a_stable_code() -> None:
    fast = FakeLanguageModelProvider(model_identifier="fast", environment="test")
    reasoning = FakeLanguageModelProvider(model_identifier="reasoning", environment="test")
    selector = DeterministicModelProviderSelector(fast, reasoning)
    router = DeterministicIntentRouter(0.75)

    memory = selector.select(router.classify("What do you remember about my preferences?"), "What do you remember about my preferences?")
    complex_question = selector.select(router.classify("Compare these options step by step?"), "Compare these options step by step?")

    assert (memory.tier, memory.reason_code, memory.provider) == (ModelTier.REASONING, ModelTierReasonCode.REASONING_MEMORY, reasoning)
    assert (complex_question.tier, complex_question.reason_code, complex_question.provider) == (
        ModelTier.REASONING,
        ModelTierReasonCode.REASONING_COMPLEX_QUESTION,
        reasoning,
    )
