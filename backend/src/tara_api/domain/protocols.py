"""Framework-independent ports for the safety and tool execution boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from tara_api.domain.models import (
    ActionRiskLevel,
    AuditEvent,
    ConfirmationAuthorization,
    JsonValue,
    PendingConfirmation,
    PermissionScope,
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class Tool(Protocol):
    """A privileged adapter that is executed only by the central executor."""

    definition: ToolDefinition

    def validate_arguments(self, arguments: Mapping[str, JsonValue]) -> dict[str, object]: ...

    async def execute(self, request: ToolRequest, validated_arguments: dict[str, object]) -> ToolResult: ...


class ToolRegistry(Protocol):
    def get(self, tool_name: str) -> Tool | None: ...


class PermissionService(Protocol):
    def is_allowed(self, scope: PermissionScope, request: ToolRequest) -> bool: ...


class ActionPolicyService(Protocol):
    def classify(self, definition: ToolDefinition, request: ToolRequest) -> ActionRiskLevel: ...

    def requires_confirmation(self, risk_level: ActionRiskLevel) -> bool: ...


class ConfirmationService(Protocol):
    async def create(self, request: ToolRequest, definition: ToolDefinition) -> PendingConfirmation: ...

    async def respond(self, confirmation_id: UUID, response: str) -> ConfirmationAuthorization | None: ...

    async def consume(self, authorization: ConfirmationAuthorization, request: ToolRequest) -> bool: ...


class ToolExecutor(Protocol):
    async def execute(
        self,
        request: ToolRequest,
        authorization: ConfirmationAuthorization | None = None,
    ) -> ToolResult: ...


class AuditPublisher(Protocol):
    async def publish(self, event: AuditEvent) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
