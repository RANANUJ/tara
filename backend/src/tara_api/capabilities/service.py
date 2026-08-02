"""Authenticated M13 capability discovery and read-only execution service."""

from __future__ import annotations

from uuid import uuid4

from tara_api.auth.service import AuthenticationService
from tara_api.capabilities.registry import CapabilityRegistry
from tara_api.domain.auth import AuthenticatedOwnerContext
from tara_api.domain.capabilities import CapabilityDescriptor
from tara_api.domain.models import ToolRequest, ToolResult, ToolResultStatus
from tara_api.domain.protocols import ToolExecutor


class CapabilityService:
    def __init__(self, registry: CapabilityRegistry, executor: ToolExecutor, authentication: AuthenticationService) -> None:
        self._registry = registry
        self._executor = executor
        self._authentication = authentication

    def list(self) -> tuple[CapabilityDescriptor, ...]:
        return self._registry.list()

    async def list_folder(self, context: AuthenticatedOwnerContext, target: str) -> ToolResult:
        if not await self._authentication.is_context_active(context):
            return ToolResult(ToolResultStatus.DENIED, "Session is no longer active")
        request = ToolRequest("filesystem.list", "1", {"target": target}, request_id=uuid4())
        return await self._executor.execute(request)
