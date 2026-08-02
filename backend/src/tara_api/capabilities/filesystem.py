"""Constrained read-only local filesystem tool with canonical allowlist enforcement."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tara_api.domain.errors import ToolArgumentValidationError
from tara_api.domain.models import ActionRiskLevel, JsonValue, PermissionScope, ToolDefinition, ToolRequest, ToolResult, ToolResultStatus

MAX_TARGET_CHARS = 512
MAX_ENTRIES = 100


@dataclass(frozen=True, slots=True)
class FilesystemEntry:
    name: str
    kind: str


class AllowlistedFilesystemListTool:
    """List one configured local directory without following roots through traversal or links."""

    definition = ToolDefinition(
        name="filesystem.list",
        version="1",
        permission_scope=PermissionScope("filesystem.read"),
        risk_level=ActionRiskLevel.READ_ONLY,
        summary_template="list a configured local folder",
        timeout_seconds=5,
        idempotent=True,
    )

    def __init__(self, roots: tuple[Path, ...]) -> None:
        self._roots = tuple(root.resolve(strict=True) for root in roots)

    def validate_arguments(self, arguments: Mapping[str, JsonValue]) -> dict[str, object]:
        if set(arguments) != {"target"}:
            raise ToolArgumentValidationError("filesystem list accepts only target")
        target = arguments["target"]
        if not isinstance(target, str) or not target or len(target) > MAX_TARGET_CHARS:
            raise ToolArgumentValidationError("target is invalid")
        candidate = Path(target)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ToolArgumentValidationError("target is outside the allowlist")
        return {"target": target}

    async def execute(self, request: ToolRequest, validated_arguments: dict[str, object]) -> ToolResult:
        target = validated_arguments["target"]
        if not isinstance(target, str):
            return ToolResult(ToolResultStatus.INVALID, "Tool arguments are invalid")
        try:
            entries = await asyncio.wait_for(asyncio.to_thread(self._list, target), timeout=self.definition.timeout_seconds)
        except TimeoutError:
            return ToolResult(ToolResultStatus.FAILED, "The local read timed out")
        except (OSError, ValueError):
            return ToolResult(ToolResultStatus.DENIED, "The requested folder is unavailable")
        return ToolResult(
            ToolResultStatus.SUCCEEDED,
            f"Listed {len(entries)} entries from the configured local folder",
            {"entries": tuple({"name": entry.name, "kind": entry.kind} for entry in entries), "truncated": len(entries) == MAX_ENTRIES},
        )

    def _list(self, target: str) -> tuple[FilesystemEntry, ...]:
        resolved = self._resolve_target(target)
        if not resolved.is_dir():
            raise ValueError("target is not a directory")
        entries = sorted(resolved.iterdir(), key=lambda entry: entry.name.casefold())[:MAX_ENTRIES]
        return tuple(FilesystemEntry(entry.name, "directory" if entry.is_dir() else "file") for entry in entries)

    def _resolve_target(self, target: str) -> Path:
        for root in self._roots:
            resolved = (root / target).resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return resolved
        raise ValueError("target is outside the allowlist")
