import { describe, expect, it } from "vitest";

import { parseCapabilities } from "../../lib/actions";

describe("parseCapabilities", () => {
  it("accepts only complete server acknowledgements", () => {
    expect(parseCapabilities([{ name: "filesystem.read", label: "Local", state: "available", read_only: true, summary: "Safe" }])).toHaveLength(1);
    expect(parseCapabilities([{ name: "filesystem.read" }])).toEqual([]);
  });
});
