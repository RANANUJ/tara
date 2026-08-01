import { describe, expect, it } from "vitest";
import { AUDIO_FORMAT, validateAudioFormat } from "../../lib/audio";

describe("foreground audio format", () => {
  it("accepts only canonical 16 kHz mono PCM", () => {
    expect(() => validateAudioFormat(AUDIO_FORMAT)).not.toThrow();
    expect(() => validateAudioFormat({ ...AUDIO_FORMAT, channels: 2 })).toThrow("Unsupported foreground audio format");
  });
});
