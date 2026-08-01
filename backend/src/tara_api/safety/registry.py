"""In-memory registry for reviewed tool adapters."""

from tara_api.domain.protocols import Tool


class InMemoryToolRegistry:
    """Register unique tool names for use by the central safety executor."""

    def __init__(self, tools: tuple[Tool, ...] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.definition.name in self._tools:
            raise ValueError("tool names must be unique")
        self._tools[tool.definition.name] = tool

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)
