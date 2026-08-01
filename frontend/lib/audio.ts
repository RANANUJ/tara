export const AUDIO_FORMAT = { sampleRate: 16000, channels: 1, sampleWidthBytes: 2, frameMs: 20 } as const;
export const PCM_FRAME_BYTES = 640;

export function floatToPcm16(samples: Float32Array): Int16Array {
  return Int16Array.from(samples, (sample) => Math.round(Math.max(-1, Math.min(1, sample)) * 32767));
}

export function frameAudio(audioSessionId: string, sequence: number, pcm: Int16Array): ArrayBuffer {
  if (pcm.byteLength !== PCM_FRAME_BYTES || !Number.isInteger(sequence) || sequence < 0) throw new Error("Invalid PCM frame.");
  const identifier = audioSessionId.replaceAll("-", "");
  if (!/^[0-9a-f]{32}$/i.test(identifier)) throw new Error("Invalid audio session ID.");
  const bytes = new Uint8Array(24 + pcm.byteLength);
  bytes.set([0x54, 0x41, 0x52, 0x31]);
  for (let index = 0; index < 16; index += 1) bytes[4 + index] = Number.parseInt(identifier.slice(index * 2, index * 2 + 2), 16);
  new DataView(bytes.buffer).setUint32(20, sequence);
  bytes.set(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength), 24);
  return bytes.buffer;
}
