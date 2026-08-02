"""Configured capability catalog that exposes no execution path for unavailable states."""

from __future__ import annotations

from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.domain.capabilities import CapabilityDescriptor, CapabilityState
from tara_api.domain.protocols import Tool


class CapabilityRegistry:
    def __init__(self, filesystem_tool: AllowlistedFilesystemListTool | None, filesystem_state: CapabilityState | None = None) -> None:
        self._filesystem_tool = filesystem_tool
        state = filesystem_state or (CapabilityState.AVAILABLE if filesystem_tool is not None else CapabilityState.DISABLED)
        self._capabilities = (
            CapabilityDescriptor("filesystem.read", "Local folder listing", state, True, "Lists names only inside configured local folders."),
            CapabilityDescriptor("calls.place", "Phone calls", CapabilityState.REQUIRES_NATIVE_BRIDGE, False, "Requires an approved native bridge."),
            CapabilityDescriptor("messages.send", "Messages", CapabilityState.UNAVAILABLE, False, "Not implemented in this milestone."),
        )

    def list(self) -> tuple[CapabilityDescriptor, ...]:
        return self._capabilities

    def get(self, tool_name: str) -> Tool | None:
        if tool_name == "filesystem.list" and self._filesystem_tool is not None:
            return self._filesystem_tool
        return None
