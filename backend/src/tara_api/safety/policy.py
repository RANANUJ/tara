"""Server-owned deterministic action risk classification."""

from tara_api.domain.models import ActionRiskLevel, ToolDefinition, ToolRequest


class DeterministicActionPolicyService:
    """Classify actions without model input and require confirmation when consequential."""

    def classify(self, definition: ToolDefinition, request: ToolRequest) -> ActionRiskLevel:
        name = definition.name.lower()
        capability = definition.permission_scope.capability.lower()
        if "call" in name or capability.startswith("calls."):
            return ActionRiskLevel.CALL
        if "financial" in name or capability.startswith("financial."):
            return ActionRiskLevel.FINANCIAL
        if "delete" in name or capability.endswith(".delete"):
            return ActionRiskLevel.DESTRUCTIVE
        if "message" in name or capability.startswith("messages."):
            return ActionRiskLevel.OUTWARD_FACING
        return definition.risk_level

    def requires_confirmation(self, risk_level: ActionRiskLevel) -> bool:
        return risk_level in {
            ActionRiskLevel.OUTWARD_FACING,
            ActionRiskLevel.DESTRUCTIVE,
            ActionRiskLevel.FINANCIAL,
            ActionRiskLevel.CALL,
        }
