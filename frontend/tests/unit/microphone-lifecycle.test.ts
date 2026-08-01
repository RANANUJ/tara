import { describe, expect, it, vi } from "vitest";
import { ForegroundMicrophoneCapture } from "../../lib/microphone";

function installMediaDevices(getUserMedia: ReturnType<typeof vi.fn>): void {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
}

describe("foreground microphone lifecycle", () => {
  it("does not capture on construction and releases tracks and context idempotently", async () => {
    const track = { stop: vi.fn() } as unknown as MediaStreamTrack;
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] } as unknown as MediaStream);
    const close = vi.fn().mockResolvedValue(undefined);
    installMediaDevices(getUserMedia);
    const capture = new ForegroundMicrophoneCapture({ createAudioContext: () => ({ close }) });
    expect(getUserMedia).not.toHaveBeenCalled();
    await capture.startFromUserGesture();
    await capture.stop();
    await capture.cancel();
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
    expect(capture.state).toBe("idle");
  });

  it("cleans up foreground capture when the page becomes hidden", async () => {
    const track = { stop: vi.fn() } as unknown as MediaStreamTrack;
    installMediaDevices(vi.fn().mockResolvedValue({ getTracks: () => [track] } as unknown as MediaStream));
    const capture = new ForegroundMicrophoneCapture();
    await capture.startFromUserGesture();
    await capture.handlePageLifecycleChange(true);
    expect(track.stop).toHaveBeenCalledOnce();
  });
});
