/**
 * Binary-read integrity helpers for phone file transfers.
 *
 * Sources like expo-file-system may hand back a Uint8Array that is only a
 * VIEW into a larger pooled ArrayBuffer. Hashing or uploading `view.buffer`
 * raw would then include surrounding garbage bytes — producing a transfer
 * that verifies against its own (wrong) digest yet arrives unreadable
 * (e.g. shifted JPEG magic bytes). Always normalize through here first.
 */

/** Copies a Uint8Array view into an exactly-sized ArrayBuffer. */
export function toExactArrayBuffer(view: Uint8Array): ArrayBuffer {
  if (view.byteOffset === 0 && view.buffer.byteLength === view.byteLength) {
    return view.buffer as ArrayBuffer;
  }
  const out = new Uint8Array(view.byteLength);
  out.set(view);
  return out.buffer;
}

/**
 * Validates a read buffer: non-empty and (when the true size is known)
 * exactly matching it. Returns the buffer or null when it must be rejected
 * so the caller tries the next read method instead of sending bad bytes.
 */
export function acceptReadBuffer(
  buf: ArrayBuffer | null | undefined,
  expectedSize: number | null
): ArrayBuffer | null {
  if (!buf || buf.byteLength === 0) return null;
  if (expectedSize !== null && buf.byteLength !== expectedSize) return null;
  return buf;
}
