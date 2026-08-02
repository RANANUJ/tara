export type ForegroundWakeWordState = "disabled" | "ready" | "listening" | "detected" | "cooldown" | "unavailable" | "failed";

export interface ForegroundWakeWordCapabilities {
  foregroundWeb: true;
  streamingAudio: boolean;
  continuousListening: boolean;
  nativeBackground: false;
  screenOff: false;
  lockedDevice: false;
}

export interface ForegroundWakeWordOptions {
  isMicrophoneActive: () => boolean;
  isMicrophonePermissionGranted: () => boolean;
  isSocketConnected: () => boolean;
  isTtsPlaying?: () => boolean;
}

/**
 * Lifecycle guard for a foreground-only detector. It never captures, stores,
 * logs, or transmits audio and it cannot invoke an agent request on detection.
 */
export class ForegroundWakeWordController {
  state: ForegroundWakeWordState = "disabled";
  private enabled = false;
  private pageVisible = true;

  constructor(private readonly options: ForegroundWakeWordOptions) {}

  get capabilities(): ForegroundWakeWordCapabilities {
    const active = this.canListen();
    return {
      foregroundWeb: true,
      streamingAudio: active,
      continuousListening: active,
      nativeBackground: false,
      screenOff: false,
      lockedDevice: false,
    };
  }

  enable(): void {
    this.enabled = true;
    this.refresh();
  }

  disable(): void {
    this.enabled = false;
    this.state = "disabled";
  }

  onPageVisibilityChange(hidden: boolean): void {
    this.pageVisible = !hidden;
    this.refresh();
  }

  onAudioContextSuspended(): void {
    if (this.enabled) this.state = "ready";
  }

  onSocketClosed(): void {
    this.enabled = false;
    this.state = "disabled";
  }

  onPermissionRevoked(): void {
    this.state = "unavailable";
  }

  onDeviceChange(): void {
    if (this.enabled) this.state = "ready";
  }

  onTtsPlaybackChange(): void {
    this.refresh();
  }

  onWakeDetected(): void {
    if (this.state === "listening") this.state = "detected";
  }

  enterCooldown(): void {
    if (this.state === "detected") this.state = "cooldown";
  }

  completeCooldown(): void {
    if (this.state === "cooldown") this.refresh();
  }

  dispose(): void {
    this.disable();
  }

  private refresh(): void {
    if (!this.enabled) {
      this.state = "disabled";
    } else if (!this.options.isMicrophonePermissionGranted()) {
      this.state = "unavailable";
    } else if (this.canListen()) {
      this.state = "listening";
    } else {
      this.state = "ready";
    }
  }

  private canListen(): boolean {
    return this.enabled && this.pageVisible && this.options.isMicrophonePermissionGranted() && this.options.isMicrophoneActive() && this.options.isSocketConnected() && !this.options.isTtsPlaying?.();
  }
}
