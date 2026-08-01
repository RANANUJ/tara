import { describe, expect, it, vi } from "vitest";
import { ForegroundMicrophoneCapture, MicrophoneCaptureError } from "../../lib/microphone";

function installMediaDevices(value: object | undefined): void {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value });
}

describe("foreground microphone permissions", () => {
  it("maps denial and missing hardware to typed safe errors", async () => {
    installMediaDevices({ getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")) });
    await expect(new ForegroundMicrophoneCapture().startFromUserGesture()).rejects.toMatchObject({ code: "permission_denied" } satisfies Partial<MicrophoneCaptureError>);
    installMediaDevices({ getUserMedia: vi.fn().mockRejectedValue(new DOMException("none", "NotFoundError")) });
    await expect(new ForegroundMicrophoneCapture().startFromUserGesture()).rejects.toMatchObject({ code: "no_device" } satisfies Partial<MicrophoneCaptureError>);
  });

  it("reports unsupported capture without attempting an automatic restart", async () => {
    installMediaDevices(undefined);
    await expect(new ForegroundMicrophoneCapture().startFromUserGesture()).rejects.toMatchObject({ code: "unavailable" } satisfies Partial<MicrophoneCaptureError>);
  });
});
