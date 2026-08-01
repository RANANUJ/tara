export const AUDIO_FORMAT = {
  sampleRate: 16000,
  channels: 1,
  sampleWidthBytes: 2,
  frameMs: 20,
  endianness: "little",
} as const;

export const PCM_FRAME_SAMPLES = 320;
export const PCM_FRAME_BYTES = PCM_FRAME_SAMPLES * AUDIO_FORMAT.sampleWidthBytes;
export const AUDIO_FRAME_HEADER_BYTES = 24;
export const AUDIO_FRAME_BYTES = AUDIO_FRAME_HEADER_BYTES + PCM_FRAME_BYTES;

export interface AudioFormat {
  sampleRate: number;
  channels: number;
  sampleWidthBytes: number;
  frameMs: number;
  endianness: string;
}

export function validateAudioFormat(format: AudioFormat): void {
  if (format.sampleRate !== 16000 || format.channels !== 1 || format.sampleWidthBytes !== 2 || format.frameMs !== 20 || format.endianness !== "little") {
    throw new Error("Unsupported foreground audio format.");
  }
}

export function downmixToMono(channels: readonly Float32Array[]): Float32Array {
  if (channels.length === 0 || channels.some((channel) => channel.length !== channels[0]?.length)) throw new Error("Invalid audio channels.");
  const mono = new Float32Array(channels[0].length);
  for (let sampleIndex = 0; sampleIndex < mono.length; sampleIndex += 1) {
    mono[sampleIndex] = channels.reduce((sum, channel) => sum + channel[sampleIndex], 0) / channels.length;
  }
  return mono;
}

export function resampleTo16Khz(samples: Float32Array, inputSampleRate: number): Float32Array {
  if (!Number.isInteger(inputSampleRate) || inputSampleRate <= 0) throw new Error("Invalid input sample rate.");
  if (inputSampleRate === AUDIO_FORMAT.sampleRate) return new Float32Array(samples);
  const outputLength = Math.round((samples.length * AUDIO_FORMAT.sampleRate) / inputSampleRate);
  const output = new Float32Array(outputLength);
  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const sourcePosition = (outputIndex * inputSampleRate) / AUDIO_FORMAT.sampleRate;
    const leftIndex = Math.min(Math.floor(sourcePosition), Math.max(0, samples.length - 1));
    const rightIndex = Math.min(leftIndex + 1, Math.max(0, samples.length - 1));
    const fraction = sourcePosition - leftIndex;
    output[outputIndex] = samples[leftIndex] * (1 - fraction) + samples[rightIndex] * fraction;
  }
  return output;
}

export function floatToPcm16(samples: Float32Array): Int16Array {
  return Int16Array.from(samples, (sample) => {
    const clamped = Math.max(-1, Math.min(1, Number.isFinite(sample) ? sample : 0));
    return clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
  });
}

export function pcm16ToLittleEndian(samples: Int16Array): Uint8Array {
  const bytes = new Uint8Array(samples.length * AUDIO_FORMAT.sampleWidthBytes);
  const view = new DataView(bytes.buffer);
  samples.forEach((sample, index) => view.setInt16(index * AUDIO_FORMAT.sampleWidthBytes, sample, true));
  return bytes;
}

export function frameAudio(audioSessionId: string, sequence: number, pcm: Int16Array): ArrayBuffer {
  if (pcm.byteLength !== PCM_FRAME_BYTES || !Number.isInteger(sequence) || sequence < 0 || sequence > 0xffffffff) throw new Error("Invalid PCM frame.");
  const identifier = audioSessionId.replaceAll("-", "");
  if (!/^[0-9a-f]{32}$/i.test(identifier)) throw new Error("Invalid audio session ID.");
  const bytes = new Uint8Array(AUDIO_FRAME_BYTES);
  bytes.set([0x54, 0x41, 0x52, 0x31]);
  for (let index = 0; index < 16; index += 1) bytes[4 + index] = Number.parseInt(identifier.slice(index * 2, index * 2 + 2), 16);
  new DataView(bytes.buffer).setUint32(20, sequence);
  bytes.set(pcm16ToLittleEndian(pcm), AUDIO_FRAME_HEADER_BYTES);
  return bytes.buffer;
}
