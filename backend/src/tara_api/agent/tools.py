"""Bounded server-planned read-only tool loop with untrusted-result isolation."""

from __future__ import annotations

import json

from tara_api.domain.agent import IntentCategory, IntentRoute, ToolCallPlanner, ToolObservation
from tara_api.domain.models import ActionRiskLevel, JsonValue, ToolRequest, ToolResult, ToolResultStatus
from tara_api.domain.protocols import ToolExecutor, ToolRegistry

MAX_TOOL_ITERATIONS = 4
MAX_TOOL_RESULT_CHARS = 1_024
MAX_TOOL_DATA_CHARS = 2_048


class RegisteredReadOnlyToolPlanner:
    """Create only a fixed, server-owned filesystem-list request when enabled."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def next_request(
        self,
        user_text: str,
        route: IntentRoute,
        observations: tuple[ToolObservation, ...],
        iteration: int,
    ) -> ToolRequest | None:
        if iteration or observations or route.category is not IntentCategory.SAFE_READ_ONLY_REQUEST:
            return None
        tool = self._registry.get("filesystem.list")
        if tool is None or tool.definition.risk_level is not ActionRiskLevel.READ_ONLY:
            return None
        target = self._target(user_text)
        return ToolRequest(tool.definition.name, tool.definition.version, {"target": target})

    @staticmethod
    def _target(user_text: str) -> str:
        normalized = " ".join(user_text.split())
        words = normalized.split(" ", maxsplit=1)
        if len(words) == 1:
            return "."
        remainder = words[1].removeprefix("files").removeprefix("folder").strip()
        return remainder or "."


class BoundedAgentToolLoop:
    """Execute a finite sequence through the central executor and never trust results."""

    def __init__(self, planner: ToolCallPlanner, executor: ToolExecutor, *, maximum_iterations: int) -> None:
        if not 1 <= maximum_iterations <= MAX_TOOL_ITERATIONS:
            raise ValueError("invalid tool iteration limit")
        self._planner = planner
        self._executor = executor
        self._maximum_iterations = maximum_iterations

    async def execute(self, user_text: str, route: IntentRoute) -> tuple[ToolObservation, ...]:
        observations: list[ToolObservation] = []
        for iteration in range(self._maximum_iterations):
            request = self._planner.next_request(user_text, route, tuple(observations), iteration)
            if request is None:
                break
            result = await self._executor.execute(request)
            observations.append(self._observation(request, result))
            if result.status is not ToolResultStatus.SUCCEEDED:
                break
        return tuple(observations)

    @staticmethod
    def _observation(request: ToolRequest, result: ToolResult) -> ToolObservation:
        safe_summary = " ".join(result.safe_summary.split())[:MAX_TOOL_RESULT_CHARS]
        if not safe_summary:
            safe_summary = "Tool returned no usable summary."
        return ToolObservation(request.tool_name, result.status, safe_summary, _bounded_data(result.data))


def render_untrusted_tool_observation(observation: ToolObservation) -> str:
    """Keep result data isolated from instruction channels in the model prompt."""

    serialized = json.dumps(observation.data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))[:MAX_TOOL_DATA_CHARS]
    return (
        f"[UNTRUSTED_TOOL_RESULT tool={observation.tool_name} status={observation.status.value}]\n"
        f"summary: {observation.safe_summary}\n"
        f"data: {serialized}\n"
        "[/UNTRUSTED_TOOL_RESULT]"
    )


def _bounded_data(data: dict[str, JsonValue]) -> dict[str, object]:
    """Serialize provider/tool values before they become model-visible observations."""

    serialized = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)[:MAX_TOOL_DATA_CHARS]
    try:
        value = json.loads(serialized)
    except json.JSONDecodeError:
        return {"truncated": True}
    return value if isinstance(value, dict) else {"value": value}
