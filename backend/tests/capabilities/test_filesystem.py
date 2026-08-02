"""M13 constrained filesystem capability tests."""

from pathlib import Path

import pytest

from tara_api.capabilities.filesystem import AllowlistedFilesystemListTool
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.models import ToolRequest, ToolResultStatus


async def test_allowlisted_list_returns_names_without_file_content(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("private fixture content", encoding="utf-8")
    tool = AllowlistedFilesystemListTool((root,))

    result = await tool.execute(ToolRequest("filesystem.list", "1", {"target": "."}), tool.validate_arguments({"target": "."}))

    assert result.status == ToolResultStatus.SUCCEEDED
    assert result.data["entries"] == ({"name": "safe.txt", "kind": "file"},)


def test_traversal_and_absolute_paths_fail_before_execution(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    tool = AllowlistedFilesystemListTool((root,))

    with pytest.raises(ValueError):
        tool.validate_arguments({"target": "../outside"})
    with pytest.raises(ValueError):
        tool.validate_arguments({"target": str(root)})


def test_disabled_registry_exposes_no_tool_path() -> None:
    registry = CapabilityRegistry(None)

    assert registry.get("filesystem.list") is None
    assert registry.list()[0].state.value == "disabled"
