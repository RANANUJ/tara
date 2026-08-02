export type TtsPlaybackState = "idle" | "buffering" | "playing" | "paused_by_browser" | "canceled" | "completed" | "failed";

export interface TtsFormatMetadata {
  encoding: "pcm_s16le";
  sample_rate: 16000 | 22050 | 24000;
  channels: 1;
  bit_depth: 16;
  container: "raw";
}

export interface TtsAudioStart {
  synthesis_request_id: string;
  total_bytes: number;
  total_chunks: number;
  duration_ms: number;
  format: TtsFormatMetadata;
}

export interface TtsAudioChunk {
  synthesis_request_id: string;
  sequence: number;
  byte_offset: number;
  byte_length: number;
  final: boolean;
  audio_base64: string;
}

interface PlaybackBuffer {
  getChannelData(channel: number): Float32Array;
}

interface PlaybackSource {
  buffer: PlaybackBuffer | null;
  onended: (() => void) | null;
  connect(destination: AudioNode): void;
  start(): void;
}

interface PlaybackContext {
  createBuffer(channels: number, length: number, sampleRate: number): PlaybackBuffer;
  createBufferSource(): PlaybackSource;
  destination: AudioNode;
  resume(): Promise<void>;
  state: AudioContextState;
  close(): Promise<void>;
}

export interface TtsPlaybackOptions {
  createAudioContext: () => PlaybackContext;
  sendCancel: (synthesisRequestId: string) => void;
  maximumBufferedChunks?: number;
}

export class ForegroundTtsPlayback {
  state: TtsPlaybackState = "idle";
  private context: PlaybackContext | undefined;
  private activeRequestId: string | undefined;
  private expectedSequence = 0;
  private finalSeen = false;
  private bufferedChunks = 0;
  private sampleRate = 22050;
  private readonly maximumBufferedChunks: number;

  constructor(private readonly options: TtsPlaybackOptions) {
    this.maximumBufferedChunks = options.maximumBufferedChunks ?? 4;
  }

  async activateFromUserGesture(): Promise<void> {
    this.context ??= this.options.createAudioContext();
    if (this.context.state === "suspended") {
      try {
        await this.context.resume();
      } catch {
        this.state = "paused_by_browser";
        return;
      }
    }
  }

  async start(event: TtsAudioStart): Promise<void> {
    if (!this.validStart(event)) return this.fail();
    await this.cancelActive(false);
    if (!this.context || this.context.state === "suspended") {
        this.state = "paused_by_browser";
        return;
    }
    this.activeRequestId = event.synthesis_request_id;
    this.expectedSequence = 0;
    this.finalSeen = false;
    this.bufferedChunks = 0;
    this.sampleRate = event.format.sample_rate;
    this.state = "buffering";
  }

  receiveChunk(event: TtsAudioChunk): void {
    if (!this.activeRequestId || event.synthesis_request_id !== this.activeRequestId || event.sequence !== this.expectedSequence || this.finalSeen || this.bufferedChunks >= this.maximumBufferedChunks) {
      this.fail();
      return;
    }
    const bytes = decodeBase64(event.audio_base64);
    if (!bytes || bytes.byteLength !== event.byte_length || event.byte_offset < 0 || event.byte_length === 0 || event.byte_length % 2 !== 0) {
      this.fail();
      return;
    }
    const context = this.context;
    if (!context || context.state === "suspended") {
      this.state = "paused_by_browser";
      return;
    }
    this.bufferedChunks += 1;
    try {
      const buffer = context.createBuffer(1, bytes.byteLength / 2, this.sampleRate);
      const data = buffer.getChannelData(0);
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      for (let index = 0; index < data.length; index += 1) data[index] = view.getInt16(index * 2, true) / 32768;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.onended = () => {
        this.bufferedChunks = Math.max(0, this.bufferedChunks - 1);
      };
      source.connect(context.destination);
      source.start();
      this.expectedSequence += 1;
      this.finalSeen = event.final;
      this.state = "playing";
    } catch {
      this.fail();
    }
  }

  end(synthesisRequestId: string): void {
    if (synthesisRequestId !== this.activeRequestId || !this.finalSeen) return this.fail();
    this.clearStream();
    this.state = "completed";
  }

  async stop(): Promise<void> {
    await this.cancelActive(true);
  }

  async onVadSpeechStarted(microphoneActive: boolean): Promise<void> {
    if (microphoneActive && this.state === "playing") await this.stop();
  }

  async onSocketClosed(): Promise<void> {
    await this.cancelActive(false);
  }

  private validStart(event: TtsAudioStart): boolean {
    const format = event.format;
    return Boolean(event.synthesis_request_id) && event.total_bytes >= 0 && event.total_chunks > 0 && event.duration_ms >= 0 && format.encoding === "pcm_s16le" && format.channels === 1 && format.bit_depth === 16 && format.container === "raw";
  }

  private async cancelActive(notifyServer: boolean): Promise<void> {
    const requestId = this.activeRequestId;
    this.clearStream();
    if (requestId && notifyServer) this.options.sendCancel(requestId);
    if (requestId) this.state = "canceled";
  }

  private clearStream(): void {
    this.activeRequestId = undefined;
    this.expectedSequence = 0;
    this.finalSeen = false;
    this.bufferedChunks = 0;
  }

  private fail(): void {
    this.clearStream();
    this.state = "failed";
  }
}

function decodeBase64(value: string): Uint8Array | undefined {
  try {
    const text = atob(value);
    return Uint8Array.from(text, (character) => character.charCodeAt(0));
  } catch {
    return undefined;
  }
}
