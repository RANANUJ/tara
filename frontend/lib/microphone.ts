export type CaptureState = "idle" | "requesting_permission" | "capturing" | "error";

export class ForegroundMicrophoneCapture {
  state: CaptureState = "idle";
  private stream: MediaStream | undefined;

  async startFromUserGesture(): Promise<MediaStream> {
    if (this.state !== "idle") throw new Error("Capture is already active.");
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone capture is unavailable.");
    this.state = "requesting_permission";
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 }, video: false });
      this.state = "capturing";
      return this.stream;
    } catch (error) {
      this.state = "error";
      throw error;
    }
  }

  stop(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
    this.state = "idle";
  }
}
