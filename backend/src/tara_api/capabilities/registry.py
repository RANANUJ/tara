"""Configured capability catalog that exposes no execution path for unavailable states."""

from __future__ import annotations

from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.domain.capabilities import CapabilityDescriptor, CapabilityState
from tara_api.domain.models import ActionRiskLevel
from tara_api.domain.protocols import Tool


class CapabilityRegistry:
    def __init__(
        self,
        filesystem_tool: AllowlistedFilesystemListTool | None,
        filesystem_state: CapabilityState | None = None,
        additional_tools: tuple[Tool, ...] = (),
    ) -> None:
        self._filesystem_tool = filesystem_tool
        state = filesystem_state or (CapabilityState.AVAILABLE if filesystem_tool is not None else CapabilityState.DISABLED)
        capabilities = [
            CapabilityDescriptor("filesystem.read", "Local folder listing", state, True, "Lists names only inside configured local folders."),
            CapabilityDescriptor("calls.place", "Phone calls", CapabilityState.REQUIRES_NATIVE_BRIDGE, False, "Requires an approved native bridge."),
            CapabilityDescriptor("messages.send", "Messages", CapabilityState.UNAVAILABLE, False, "Not implemented in this milestone."),
        ]
        self._tools: dict[str, Tool] = {}
        if filesystem_tool is not None and state is CapabilityState.AVAILABLE:
            self._tools[filesystem_tool.definition.name] = filesystem_tool
        for tool in additional_tools:
            if tool.definition.name in self._tools:
                raise ValueError("duplicate_capability")
            self._tools[tool.definition.name] = tool
            capabilities.append(
                CapabilityDescriptor(
                    tool.definition.name,
                    tool.definition.name,
                    CapabilityState.AVAILABLE,
                    tool.definition.risk_level is ActionRiskLevel.READ_ONLY,
                    tool.definition.summary_template,
                )
            )
        self._capabilities = tuple(capabilities)

    def list(self) -> tuple[CapabilityDescriptor, ...]:
        return self._capabilities

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)
