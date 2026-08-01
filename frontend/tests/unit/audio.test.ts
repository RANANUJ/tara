import { describe, expect, it } from "vitest";
import { PCM_FRAME_BYTES, floatToPcm16, frameAudio } from "../../lib/audio";

describe("M7 audio framing", () => {
  it("converts and frames canonical PCM without persistence", () => {
    expect([...floatToPcm16(new Float32Array([-2, 0, 2]))]).toEqual([-32767, 0, 32767]);
    const frame = frameAudio("123e4567-e89b-12d3-a456-426614174000", 2, new Int16Array(PCM_FRAME_BYTES / 2));
    expect(new Uint8Array(frame).slice(0, 4)).toEqual(new Uint8Array([0x54, 0x41, 0x52, 0x31]));
  });
});
