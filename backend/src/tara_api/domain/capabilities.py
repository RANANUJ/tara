"""Framework-neutral capability catalog contracts for safe tool discovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    REQUIRES_NATIVE_BRIDGE = "requires_native_bridge"


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    name: str
    label: str
    state: CapabilityState
    read_only: bool
    safe_summary: str

    def __post_init__(self) -> None:
        if not self.name or not self.label or not self.safe_summary:
            raise ValueError("capability metadata is required")

