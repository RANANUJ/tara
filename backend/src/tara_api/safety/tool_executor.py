"""Central tool execution path that cannot skip policy, permission, or confirmation."""

from tara_api.domain.errors import ToolArgumentValidationError
from tara_api.domain.models import (
    AuditEvent,
    ConfirmationAuthorization,
    JsonValue,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
)
from tara_api.domain.protocols import (
    ActionPolicyService,
    AuditPublisher,
    Clock,
    ConfirmationService,
    PermissionService,
    ToolRegistry,
)


class SafetyToolExecutor:
    """Validate and gate every tool invocation before a privileged adapter is called."""

    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionService,
        policy: ActionPolicyService,
        confirmations: ConfirmationService,
        audit_publisher: AuditPublisher,
        clock: Clock,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._policy = policy
        self._confirmations = confirmations
        self._audit_publisher = audit_publisher
        self._clock = clock

    async def execute(
        self,
        request: ToolRequest,
        authorization: ConfirmationAuthorization | None = None,
    ) -> ToolResult:
        tool = self._registry.get(request.tool_name)
        if tool is None:
            return await self._deny(request, ToolResultStatus.UNKNOWN_TOOL, "Unknown tool")
        if tool.definition.version != request.schema_version:
            return await self._deny(request, ToolResultStatus.INVALID, "Unsupported tool schema version")
        try:
            validated_arguments = tool.validate_arguments(request.arguments)
        except (TypeError, ValueError, ToolArgumentValidationError):
            return await self._deny(request, ToolResultStatus.INVALID, "Tool arguments are invalid")
        if not self._permissions.is_allowed(tool.definition.permission_scope, request):
            return await self._deny(request, ToolResultStatus.DENIED, "Permission denied")

        risk_level = self._policy.classify(tool.definition, request)
        if self._policy.requires_confirmation(risk_level):
            if authorization is None:
                confirmation = await self._confirmations.create(request, tool.definition)
                await self._publish("tool.confirmation_required", "awaiting_confirmation", request, risk_level.value)
                return ToolResult(
                    status=ToolResultStatus.CONFIRMATION_REQUIRED,
                    safe_summary=confirmation.prompt,
                    confirmation=confirmation,
                )
            if not await self._confirmations.consume(authorization, request):
                return await self._deny(request, ToolResultStatus.DENIED, "Confirmation is invalid or already used")

        result = await tool.execute(request, validated_arguments)
        await self._publish("tool.executed", result.status.value, request, risk_level.value)
        return result

    async def _deny(self, request: ToolRequest, status: ToolResultStatus, summary: str) -> ToolResult:
        await self._publish("tool.denied", status.value, request, None)
        return ToolResult(status=status, safe_summary=summary)

    async def _publish(
        self,
        event_type: str,
        outcome: str,
        request: ToolRequest,
        risk_level: str | None,
    ) -> None:
        metadata: dict[str, JsonValue] = {
            "tool_name": request.tool_name,
            "request_hash_prefix": request.canonical_hash()[:12],
        }
        if risk_level is not None:
            metadata["risk_level"] = risk_level
        await self._audit_publisher.publish(
            AuditEvent(
                event_type=event_type,
                outcome=outcome,
                occurred_at=self._clock.now(),
                subject_reference=str(request.request_id),
                safe_metadata=metadata,
            )
        )
