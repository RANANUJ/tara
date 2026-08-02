import { describe, expect, it, vi } from "vitest";

import { ForegroundTtsPlayback } from "../../lib/tts-playback";

function context(state: "running" | "suspended" = "running") {
  const source = { connect: vi.fn(), start: vi.fn(), buffer: null, onended: null as (() => void) | null };
  return {
    createBuffer: vi.fn(() => ({ getChannelData: () => new Float32Array(2) })),
    createBufferSource: vi.fn(() => source),
    destination: {} as AudioNode,
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    state,
  };
}

const format = { encoding: "pcm_s16le" as const, sample_rate: 22050 as const, channels: 1 as const, bit_depth: 16 as const, container: "raw" as const };
const start = (id = "tts-1") => ({ synthesis_request_id: id, total_bytes: 4, total_chunks: 1, duration_ms: 1, format });
const chunk = (id = "tts-1", sequence = 0, final = true) => ({ synthesis_request_id: id, sequence, byte_offset: sequence * 4, byte_length: 4, final, audio_base64: "AAAAAA==" });

describe("foreground TTS playback", () => {
  it("accepts ordered PCM chunks and completes", async () => {
    const audio = context();
    const playback = new ForegroundTtsPlayback({ createAudioContext: () => audio, sendCancel: vi.fn() });
    await playback.activateFromUserGesture();
    await playback.start(start());
    playback.receiveChunk(chunk());
    playback.end("tts-1");
    expect(playback.state).toBe("completed");
    expect(audio.createBufferSource).toHaveBeenCalledOnce();
  });

  it("fails closed for duplicate or out-of-order chunks", async () => {
    const playback = new ForegroundTtsPlayback({ createAudioContext: () => context(), sendCancel: vi.fn() });
    await playback.activateFromUserGesture();
    await playback.start(start());
    playback.receiveChunk(chunk("tts-1", 1));
    expect(playback.state).toBe("failed");
  });

  it("explicit stop and foreground VAD barge-in send one cancellation", async () => {
    const sendCancel = vi.fn();
    const playback = new ForegroundTtsPlayback({ createAudioContext: () => context(), sendCancel });
    await playback.activateFromUserGesture();
    await playback.start(start());
    playback.receiveChunk(chunk());
    await playback.onVadSpeechStarted(true);
    await playback.stop();
    expect(playback.state).toBe("canceled");
    expect(sendCancel).toHaveBeenCalledOnce();
  });

  it("handles browser suspension without retaining stream data", async () => {
    const audio = context("suspended");
    audio.resume.mockRejectedValueOnce(new Error("blocked"));
    const playback = new ForegroundTtsPlayback({ createAudioContext: () => audio, sendCancel: vi.fn() });
    await playback.activateFromUserGesture();
    await playback.start(start());
    expect(playback.state).toBe("paused_by_browser");
  });
});
