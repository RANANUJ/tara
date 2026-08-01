export type CaptureState = "idle" | "requesting_permission" | "capturing" | "error";
export type MicrophoneErrorCode = "permission_denied" | "no_device" | "unavailable" | "capture_failed";

export class MicrophoneCaptureError extends Error {
  constructor(
    readonly code: MicrophoneErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "MicrophoneCaptureError";
  }
}

type ClosableAudioContext = Pick<AudioContext, "close">;

export interface ForegroundMicrophoneOptions {
  createAudioContext?: () => ClosableAudioContext;
}

export class ForegroundMicrophoneCapture {
  state: CaptureState = "idle";
  private stream: MediaStream | undefined;
  private audioContext: ClosableAudioContext | undefined;

  constructor(private readonly options: ForegroundMicrophoneOptions = {}) {}

  async startFromUserGesture(): Promise<MediaStream> {
    if (this.state !== "idle") throw new MicrophoneCaptureError("capture_failed", "Capture is already active.");
    if (!navigator.mediaDevices?.getUserMedia) throw new MicrophoneCaptureError("unavailable", "Microphone capture is unavailable.");
    this.state = "requesting_permission";
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 }, video: false });
      this.audioContext = this.options.createAudioContext?.();
      this.state = "capturing";
      return this.stream;
    } catch (error) {
      await this.releaseResources();
      this.state = "error";
      throw this.toSafeError(error);
    }
  }

  async stop(): Promise<void> {
    await this.releaseResources();
    this.state = "idle";
  }

  async cancel(): Promise<void> {
    await this.stop();
  }

  async handlePageLifecycleChange(hidden: boolean): Promise<void> {
    if (hidden) await this.stop();
  }

  private async releaseResources(): Promise<void> {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
    const context = this.audioContext;
    this.audioContext = undefined;
    if (context) await context.close();
  }

  private toSafeError(error: unknown): MicrophoneCaptureError {
    const name = error instanceof DOMException ? error.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") return new MicrophoneCaptureError("permission_denied", "Microphone permission was denied.");
    if (name === "NotFoundError") return new MicrophoneCaptureError("no_device", "No microphone device is available.");
    return new MicrophoneCaptureError("capture_failed", "Microphone capture could not start.");
  }
}
