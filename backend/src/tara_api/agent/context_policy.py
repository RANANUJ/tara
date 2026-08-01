"""Policy for minimizing persisted data before it reaches a model prompt."""

from __future__ import annotations

from collections.abc import Iterable

from tara_api.domain.agent import ContextItem, ContextSensitivity


class ContextSensitivityPolicy:
    """Apply a server configuration; restricted data is never promptable."""

    def __init__(self, allowed_sensitivities: Iterable[ContextSensitivity]) -> None:
        allowed = frozenset(allowed_sensitivities)
        if ContextSensitivity.RESTRICTED in allowed:
            raise ValueError("restricted context cannot be enabled")
        self._allowed = allowed

    def allows(self, sensitivity: ContextSensitivity) -> bool:
        return sensitivity != ContextSensitivity.RESTRICTED and sensitivity in self._allowed

    def filter(self, items: Iterable[ContextItem]) -> tuple[ContextItem, ...]:
        return tuple(item for item in items if self.allows(item.sensitivity))
