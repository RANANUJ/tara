export type CapabilityState = "available" | "disabled" | "degraded" | "unavailable" | "requires_native_bridge";

export interface Capability {
  name: string;
  label: string;
  state: CapabilityState;
  read_only: boolean;
  summary: string;
}

export function parseCapabilities(value: unknown): Capability[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Capability =>
      typeof item === "object" && item !== null &&
      typeof (item as Record<string, unknown>).name === "string" &&
      typeof (item as Record<string, unknown>).label === "string" &&
      typeof (item as Record<string, unknown>).summary === "string" &&
      typeof (item as Record<string, unknown>).read_only === "boolean" &&
      ["available", "disabled", "degraded", "unavailable", "requires_native_bridge"].includes(String((item as Record<string, unknown>).state)),
  );
}
