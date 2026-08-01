"""Deterministic, conservative intent classification for the M9B boundary."""

from __future__ import annotations

import re

from tara_api.domain.agent import IntentCategory, IntentReasonCode, IntentRoute


class DeterministicIntentRouter:
    """Classify text without an LLM and never authorize an action."""

    _INFORMATIONAL_ACTION = re.compile(
        r"^(how (do|can) i|how to|what is the (way|process) to|can you explain)\b",
        re.IGNORECASE,
    )
    _CONSEQUENTIAL_PATTERNS: tuple[tuple[re.Pattern[str], IntentReasonCode], ...] = (
        (re.compile(r"^(send|message|text|email)\b|\b(send|message|text|email)\s+.+\b(to|at)\b", re.IGNORECASE), IntentReasonCode.CONSEQUENTIAL_MESSAGE),
        (re.compile(r"^(call|dial|phone|ring)\b|\b(call|dial)\s+.+\b", re.IGNORECASE), IntentReasonCode.CONSEQUENTIAL_CALL),
        (re.compile(r"^(delete|remove|erase|destroy|wipe)\b", re.IGNORECASE), IntentReasonCode.CONSEQUENTIAL_DESTRUCTIVE),
        (re.compile(r"^(pay|buy|purchase|transfer|donate|order)\b", re.IGNORECASE), IntentReasonCode.CONSEQUENTIAL_FINANCIAL),
        (re.compile(r"^(post|publish|share|upload|submit)\b", re.IGNORECASE), IntentReasonCode.CONSEQUENTIAL_EXTERNAL_WRITE),
        (re.compile(r"^(change|reset|update)\s+.*\b(password|security|account)\b|^(log out|sign out|disable)\b", re.IGNORECASE), IntentReasonCode.CONSEQUENTIAL_ACCOUNT_SECURITY),
    )
    _MEMORY = re.compile(r"\b(remember|memory|memories|my preference|my preferences)\b", re.IGNORECASE)
    _READ_ONLY = re.compile(r"^(show|list|check|look up|search|find|read|open)\b", re.IGNORECASE)
    _QUESTION = re.compile(r"^(who|what|when|where|why|which|is|are|can|could|would|will|do|does|did)\b|\?$", re.IGNORECASE)
    _AMBIGUOUS = re.compile(r"^(um+|uh+|maybe|something|whatever|help)\W*$", re.IGNORECASE)

    def __init__(self, confidence_threshold: float) -> None:
        if not 0 < confidence_threshold <= 1:
            raise ValueError("confidence threshold must be between zero and one")
        self._confidence_threshold = confidence_threshold

    def classify(self, text: str) -> IntentRoute:
        normalized = " ".join(text.split())
        if not normalized:
            raise ValueError("intent text cannot be blank")
        if self._INFORMATIONAL_ACTION.match(normalized):
            return self._route(IntentCategory.FACTUAL_QUESTION, 0.98, IntentReasonCode.INFORMATIONAL_ACTION)
        for pattern, reason_code in self._CONSEQUENTIAL_PATTERNS:
            if pattern.search(normalized):
                return self._route(IntentCategory.CONSEQUENTIAL_ACTION_REQUEST, 0.99, reason_code)
        if self._MEMORY.search(normalized):
            return self._route(IntentCategory.MEMORY_QUERY, 0.94, IntentReasonCode.MEMORY_REFERENCE)
        if self._READ_ONLY.search(normalized):
            return self._route(IntentCategory.SAFE_READ_ONLY_REQUEST, 0.88, IntentReasonCode.READ_ONLY_VERB)
        if self._QUESTION.search(normalized):
            return self._route(IntentCategory.FACTUAL_QUESTION, 0.84, IntentReasonCode.QUESTION)
        if self._AMBIGUOUS.match(normalized):
            return self._ambiguous()
        return self._route(IntentCategory.CONVERSATION, 0.8, IntentReasonCode.CONVERSATIONAL)

    def _route(self, category: IntentCategory, confidence: float, reason_code: IntentReasonCode) -> IntentRoute:
        if confidence < self._confidence_threshold:
            return self._ambiguous()
        return IntentRoute(
            category=category,
            confidence=confidence,
            reason_code=reason_code,
            consequential_risk=category == IntentCategory.CONSEQUENTIAL_ACTION_REQUEST,
        )

    def _ambiguous(self) -> IntentRoute:
        return IntentRoute(
            category=IntentCategory.AMBIGUOUS,
            confidence=min(0.49, self._confidence_threshold - 0.01),
            reason_code=IntentReasonCode.LOW_CONFIDENCE,
            clarification="Could you clarify what you would like help with?",
        )
