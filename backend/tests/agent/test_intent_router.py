import pytest

from tara_api.agent.routing import DeterministicIntentRouter
from tara_api.domain.agent import IntentCategory, IntentReasonCode


@pytest.mark.parametrize(
    ("text", "reason_code"),
    (
        ("Send a message to Sam", IntentReasonCode.CONSEQUENTIAL_MESSAGE),
        ("Call the dentist", IntentReasonCode.CONSEQUENTIAL_CALL),
        ("Delete that reminder", IntentReasonCode.CONSEQUENTIAL_DESTRUCTIVE),
        ("Pay my electricity bill", IntentReasonCode.CONSEQUENTIAL_FINANCIAL),
        ("Post this update", IntentReasonCode.CONSEQUENTIAL_EXTERNAL_WRITE),
        ("Reset my password", IntentReasonCode.CONSEQUENTIAL_ACCOUNT_SECURITY),
    ),
)
def test_router_marks_consequential_requests_without_authorizing_them(text: str, reason_code: IntentReasonCode) -> None:
    route = DeterministicIntentRouter(0.75).classify(text)

    assert route.category is IntentCategory.CONSEQUENTIAL_ACTION_REQUEST
    assert route.reason_code is reason_code
    assert route.consequential_risk is True


def test_router_distinguishes_information_about_an_action_from_the_action() -> None:
    router = DeterministicIntentRouter(0.75)

    route = router.classify("How do I send a message to Sam?")

    assert route.category is IntentCategory.FACTUAL_QUESTION
    assert route.reason_code is IntentReasonCode.INFORMATIONAL_ACTION
    assert route.consequential_risk is False


def test_router_is_deterministic_and_returns_clarification_below_threshold() -> None:
    router = DeterministicIntentRouter(0.75)

    first = router.classify("maybe")
    second = router.classify("maybe")

    assert first == second
    assert first.category is IntentCategory.AMBIGUOUS
    assert first.reason_code is IntentReasonCode.LOW_CONFIDENCE
    assert first.clarification is not None


def test_router_classifies_memory_read_only_question_and_conversation() -> None:
    router = DeterministicIntentRouter(0.75)

    assert router.classify("What do you remember about my preferences?").category is IntentCategory.MEMORY_QUERY
    assert router.classify("Show my reminders").category is IntentCategory.SAFE_READ_ONLY_REQUEST
    assert router.classify("What time is it?").category is IntentCategory.FACTUAL_QUESTION
    assert router.classify("Hello Tara").category is IntentCategory.CONVERSATION


def test_router_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match="blank"):
        DeterministicIntentRouter(0.75).classify(" \n ")
