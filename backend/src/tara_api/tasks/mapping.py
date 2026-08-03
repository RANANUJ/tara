"""Safe conversion from transient task commands to registered capability metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from tara_api.domain.models import JsonValue, ToolDefinition, ToolRequest
from tara_api.domain.protocols import ActionPolicyService, ToolRegistry
from tara_api.domain.tasks import ScheduledTaskCreateCommand


@dataclass(frozen=True, slots=True)
class MappedTaskCapability:
    definition: ToolDefinition
    capability_id: str
    risk_level: str
    confirmation_required: bool
    target_summary: str
    target_hash: str
    parameters_hash: str
    binding_hash: str


class CapabilityTaskMapper:
    """Resolve only registered tools; raw target and parameters never leave this boundary."""

    def __init__(self, registry: ToolRegistry, policy: ActionPolicyService) -> None:
        self._registry = registry
        self._policy = policy

    def map(self, command: ScheduledTaskCreateCommand) -> MappedTaskCapability:
        tool = self._registry.get(command.capability_id)
        if tool is None:
            raise ValueError("unknown_capability")
        arguments: dict[str, JsonValue] = {"target": command.target, **command.parameters}
        try:
            tool.validate_arguments(arguments)
        except (TypeError, ValueError):
            raise ValueError("invalid_capability_arguments") from None
        request = ToolRequest(tool.definition.name, tool.definition.version, arguments)
        risk = self._policy.classify(tool.definition, request)
        parameter_payload = json.dumps(
            command.parameters,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return MappedTaskCapability(
            tool.definition,
            tool.definition.name,
            risk.value,
            self._policy.requires_confirmation(risk),
            "configured target",
            sha256(command.target.strip().encode()).hexdigest(),
            sha256(parameter_payload.encode()).hexdigest(),
            command.binding_hash(),
        )
