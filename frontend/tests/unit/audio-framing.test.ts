import { describe, expect, it } from "vitest";
import { AUDIO_FRAME_BYTES, PCM_FRAME_BYTES, floatToPcm16, frameAudio } from "../../lib/audio";

describe("M7 binary audio framing", () => {
  it("clamps PCM, encodes little endian, and preserves monotonic sequence fields", () => {
    expect([...floatToPcm16(new Float32Array([-2, 0, 2, Number.NaN]))]).toEqual([-32768, 0, 32767, 0]);
    const frame = frameAudio("123e4567-e89b-12d3-a456-426614174000", 2, new Int16Array(PCM_FRAME_BYTES / 2).fill(1));
    const bytes = new Uint8Array(frame);
    expect(bytes).toHaveLength(AUDIO_FRAME_BYTES);
    expect([...bytes.slice(0, 4)]).toEqual([0x54, 0x41, 0x52, 0x31]);
    expect(new DataView(frame).getUint32(20)).toBe(2);
    expect([...bytes.slice(24, 26)]).toEqual([1, 0]);
    expect(() => frameAudio("123e4567-e89b-12d3-a456-426614174000", -1, new Int16Array(PCM_FRAME_BYTES / 2))).toThrow();
  });
});
