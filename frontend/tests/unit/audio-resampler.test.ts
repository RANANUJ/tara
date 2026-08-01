import { describe, expect, it } from "vitest";
import { downmixToMono, resampleTo16Khz } from "../../lib/audio";

describe("foreground audio conversion", () => {
  it("downmixes channels and explicitly resamples to 16 kHz", () => {
    expect([...downmixToMono([new Float32Array([0, 1]), new Float32Array([1, -1])])]).toEqual([0.5, 0]);
    const output = resampleTo16Khz(new Float32Array(480), 48000);
    expect(output).toHaveLength(160);
  });
});
