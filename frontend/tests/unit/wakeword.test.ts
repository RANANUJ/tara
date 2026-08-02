import { describe, expect, it, vi } from "vitest";

import { ForegroundWakeWordController } from "../../lib/wakeword";

function controller(overrides: Partial<{ microphone: boolean; permission: boolean; socket: boolean; tts: boolean }> = {}) {
  const values = { microphone: true, permission: true, socket: true, tts: false, ...overrides };
  return {
    values,
    controller: new ForegroundWakeWordController({
      isMicrophoneActive: () => values.microphone,
      isMicrophonePermissionGranted: () => values.permission,
      isSocketConnected: () => values.socket,
      isTtsPlaying: () => values.tts,
    }),
  };
}

describe("foreground wake-word controller", () => {
  it("requires existing foreground microphone capture before listening", () => {
    const item = controller({ microphone: false });
    item.controller.enable();
    expect(item.controller.state).toBe("ready");
    expect(item.controller.capabilities.streamingAudio).toBe(false);
  });

  it("suspends when hidden and resumes only while foreground prerequisites remain valid", () => {
    const item = controller();
    item.controller.enable();
    item.controller.onPageVisibilityChange(true);
    expect(item.controller.state).toBe("ready");
    item.values.socket = false;
    item.controller.onPageVisibilityChange(false);
    expect(item.controller.state).toBe("ready");
    item.values.socket = true;
    item.controller.onPageVisibilityChange(false);
    expect(item.controller.state).toBe("listening");
  });

  it("stops on disconnect or permission revocation without requesting capture", () => {
    const item = controller();
    item.controller.enable();
    item.controller.onPermissionRevoked();
    expect(item.controller.state).toBe("unavailable");
    item.controller.onSocketClosed();
    expect(item.controller.state).toBe("disabled");
  });

  it("suspends during Tara playback and exposes only honest capabilities", () => {
    const item = controller({ tts: true });
    item.controller.enable();
    expect(item.controller.state).toBe("ready");
    expect(item.controller.capabilities).toEqual({ foregroundWeb: true, streamingAudio: false, continuousListening: false, nativeBackground: false, screenOff: false, lockedDevice: false });
    item.values.tts = false;
    item.controller.onTtsPlaybackChange();
    expect(item.controller.state).toBe("listening");
  });

  it("only exposes listening-state transitions and cannot submit agent work", () => {
    const item = controller();
    const submitAgent = vi.fn();
    item.controller.enable();
    item.controller.onWakeDetected();
    item.controller.enterCooldown();
    item.controller.completeCooldown();
    expect(item.controller.state).toBe("listening");
    expect(submitAgent).not.toHaveBeenCalled();
  });
});
