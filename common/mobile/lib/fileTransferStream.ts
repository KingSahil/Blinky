import { toExactArrayBuffer, acceptReadBuffer } from './fileBytes';
import { StreamingSha256 } from './streamingSha256';

export const DEFAULT_STREAM_CHUNK_SIZE = 2 * 1024 * 1024; // 2 MB

/**
 * Fast Base64 to Uint8Array decoder without external dependencies.
 */
export function base64ToUint8Array(base64: string): Uint8Array {
  if (typeof atob === 'function') {
    const binary = atob(base64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }
  if (typeof Buffer !== 'undefined') {
    const buf = Buffer.from(base64, 'base64');
    return new Uint8Array(buf.buffer, buf.byteOffset, buf.length);
  }
  throw new Error('No base64 decoder available in environment');
}

/**
 * Uint8Array to Base64 encoder.
 */
export function uint8ArrayToBase64(bytes: Uint8Array): string {
  if (typeof btoa === 'function') {
    let binary = '';
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString('base64');
  }
  throw new Error('No base64 encoder available in environment');
}

/**
 * Reads a slice of a React Native / Web Blob into an ArrayBuffer.
 * In React Native (Hermes), Blobs do not implement the browser `.arrayBuffer()` method;
 * they must be read via `FileReader.readAsArrayBuffer()`.
 */
export function readBlobSliceAsArrayBuffer(
  blob: Blob,
  position: number,
  length: number
): Promise<ArrayBuffer> {
  if (length <= 0) {
    return Promise.resolve(new ArrayBuffer(0));
  }

  const slice = blob.slice(position, position + length);

  if (typeof (slice as any).arrayBuffer === 'function') {
    return (slice as any).arrayBuffer();
  }

  return new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const res = reader.result;
      if (res instanceof ArrayBuffer) {
        resolve(res);
      } else if (typeof res === 'string') {
        const base64 = res.includes(',') ? res.split(',')[1] : res;
        const bin = atob(base64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) {
          bytes[i] = bin.charCodeAt(i);
        }
        resolve(toExactArrayBuffer(bytes));
      } else {
        reject(new Error('Unexpected FileReader result type'));
      }
    };
    reader.onerror = () => reject(reader.error || new Error('FileReader failed to read blob slice'));
    reader.readAsArrayBuffer(slice);
  });
}

export interface ChunkReader {
  size: number;
  readChunk(position: number, length: number): Promise<Uint8Array>;
  close(): Promise<void>;
}

/**
 * Opens a streaming chunk reader for any file URI.
 * On React Native / Android, fetch(uri) accesses local files (including DocumentPicker
 * cache, external storage, and content:// URIs) bypassing Expo Go filesystem sandbox restrictions.
 * Chunks are sliced in native memory and read into JS in small 2 MB slices.
 */
export async function openChunkReader(uri: string): Promise<ChunkReader> {
  // Method 1: Node/Bun fallback for unit tests and local dev
  try {
    const fs = require('fs');
    if (typeof fs?.openSync === 'function') {
      const filePath = uri.startsWith('file://') ? new URL(uri).pathname : uri;
      const cleanPath = filePath.replace(/^\/([A-Za-z]:)/, '$1');
      if (fs.existsSync(cleanPath)) {
        const stat = fs.statSync(cleanPath);
        const fd = fs.openSync(cleanPath, 'r');
        return {
          size: stat.size,
          readChunk: async (pos: number, len: number) => {
            if (len <= 0) return new Uint8Array(0);
            const buf = Buffer.alloc(len);
            const bytesRead = fs.readSync(fd, buf, 0, len, pos);
            return new Uint8Array(buf.buffer, buf.byteOffset, bytesRead);
          },
          close: async () => {
            try {
              fs.closeSync(fd);
            } catch {}
          },
        };
      }
    }
  } catch {}

  // Method 2: React Native / Web fetch + Blob slice
  // This natively opens file:// (including /cache/DocumentPicker/), content://, blob:, and http(s)
  try {
    const res = await fetch(uri);
    if (res.ok || res.status === 200 || res.status === 0) {
      const blob = await res.blob();
      if (blob && typeof blob.size === 'number' && blob.size >= 0) {
        return {
          size: blob.size,
          readChunk: async (pos: number, len: number) => {
            if (len <= 0) return new Uint8Array(0);
            const buf = await readBlobSliceAsArrayBuffer(blob, pos, len);
            return new Uint8Array(buf);
          },
          close: async () => {
            if (typeof (blob as any)?.close === 'function') {
              try {
                (blob as any).close();
              } catch {}
            }
          },
        };
      }
    }
  } catch (err) {
    // console.warn('[fileTransferStream] Fetch blob failed, trying expo-file-system:', err);
  }

  // Method 3: expo-file-system/legacy fallback
  try {
    const FileSystem = require('expo-file-system/legacy');
    if (typeof FileSystem?.readAsStringAsync === 'function') {
      const info = await FileSystem.getInfoAsync(uri).catch(() => null);
      const size = info?.size || 0;
      return {
        size,
        readChunk: async (pos: number, len: number) => {
          if (len <= 0) return new Uint8Array(0);
          const b64 = await FileSystem.readAsStringAsync(uri, {
            encoding: FileSystem.EncodingType?.Base64 || 'base64',
            position: pos,
            length: len,
          });
          return base64ToUint8Array(b64);
        },
        close: async () => {},
      };
    }
  } catch {}

  throw new Error(`Unable to open file reader for URI: ${uri}`);
}

/**
 * Ensures a URI is accessible as a local filesystem path.
 */
export async function ensureLocalFile(
  uri: string
): Promise<{ localUri: string; cleanup: () => Promise<void> }> {
  return { localUri: uri, cleanup: async () => {} };
}

/**
 * Queries the filesystem / Blob subsystem for the exact file size.
 */
export async function getFileSize(uri: string): Promise<number | null> {
  try {
    const reader = await openChunkReader(uri);
    const size = reader.size;
    await reader.close();
    return size;
  } catch {
    return null;
  }
}

/**
 * Reads a slice of a file at a specific offset without loading the whole file into JS heap.
 */
export async function readChunkAsUint8Array(
  uri: string,
  position: number,
  length: number
): Promise<Uint8Array> {
  const reader = await openChunkReader(uri);
  try {
    return await reader.readChunk(position, length);
  } finally {
    await reader.close();
  }
}

/**
 * Computes SHA-256 digest of a file incrementally in streaming chunks.
 * Avoids Hermes Out-Of-Memory errors on files of any size (e.g. 40MB+ videos).
 */
export async function hashFileStreaming(
  uri: string,
  chunkSize = DEFAULT_STREAM_CHUNK_SIZE
): Promise<{ size: number; sha256: string }> {
  const reader = await openChunkReader(uri);

  try {
    const size = reader.size;

    // Empty file fast-path
    if (size === 0) {
      return {
        size: 0,
        sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      };
    }

    const hasher = new StreamingSha256();
    let offset = 0;

    while (offset < size) {
      const readLen = Math.min(chunkSize, size - offset);
      const chunk = await reader.readChunk(offset, readLen);
      if (chunk.length === 0) {
        throw new Error(`Unexpected end of file while hashing ${uri} at offset ${offset}`);
      }
      hasher.update(chunk);
      offset += chunk.length;
    }

    return {
      size: offset,
      sha256: hasher.digest(),
    };
  } finally {
    await reader.close();
  }
}

export type UploadProgressEvent = {
  id: string;
  direction: 'upload';
  bytes: number;
  total: number;
};

/**
 * Uploads a file chunk-by-chunk to the Blinky upload server.
 * Reads on-demand in small slices (2MB) so peak memory usage stays minimal.
 */
export async function uploadFileStreaming(
  options: {
    sourceUri: string;
    transferId: string;
    url: string;
    token: string;
    pin?: string;
    size: number;
    chunkSize: number;
    offset: number;
  },
  onProgress?: (event: UploadProgressEvent) => void
): Promise<{ transferId: string; uploadOffset: number; complete: boolean }> {
  const reader = await openChunkReader(options.sourceUri);

  try {
    const totalSize = options.size && options.size > 0 ? options.size : reader.size;
    let offset = options.offset || 0;
    // Cap chunk size to 2 MB to protect Hermes memory
    const maxSafeChunk = 2 * 1024 * 1024;
    const chunkSize = Math.min(options.chunkSize || maxSafeChunk, maxSafeChunk);

    while (offset < totalSize) {
      const nextEnd = Math.min(offset + chunkSize, totalSize);
      const readLen = nextEnd - offset;
      const chunkBytes = await reader.readChunk(offset, readLen);

      if (chunkBytes.length === 0) {
        throw new Error(`Selected file ended before its reported size (${offset}/${totalSize})`);
      }

      const body = toExactArrayBuffer(chunkBytes);

      const uploadRes = await fetch(options.url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${options.token}`,
          'Upload-Offset': String(offset),
          'Content-Length': String(chunkBytes.length),
          'Content-Type': 'application/octet-stream',
        },
        body,
      });

      if (uploadRes.status === 409) {
        const nextOffsetHeader = uploadRes.headers.get('Upload-Offset');
        if (nextOffsetHeader) {
          offset = parseInt(nextOffsetHeader, 10);
          continue;
        }
      }

      if (!uploadRes.ok) {
        const errorText = await uploadRes.text().catch(() => '');
        throw new Error(`Upload failed (${uploadRes.status})${errorText ? ': ' + errorText : ''}`);
      }

      const nextOffsetHeader = uploadRes.headers.get('Upload-Offset');
      const updatedOffset = nextOffsetHeader ? parseInt(nextOffsetHeader, 10) : nextEnd;
      offset = updatedOffset;

      if (onProgress) {
        onProgress({
          id: options.transferId,
          direction: 'upload',
          bytes: offset,
          total: totalSize,
        });
      }
    }

    return {
      transferId: options.transferId,
      uploadOffset: offset,
      complete: true,
    };
  } finally {
    await reader.close();
  }
}

/**
 * Reads a URI into an ArrayBuffer, using streaming chunk assembly for large files
 * to prevent base64 memory inflation from crashing the Hermes runtime.
 */
export async function readUriAsArrayBufferStreaming(uri: string): Promise<ArrayBuffer> {
  const reader = await openChunkReader(uri);

  try {
    const expected = reader.size;
    const accept = (buf: ArrayBuffer | null | undefined): ArrayBuffer | null =>
      acceptReadBuffer(buf, expected);

    const out = new Uint8Array(expected);
    let offset = 0;
    const chunkSize = DEFAULT_STREAM_CHUNK_SIZE;
    while (offset < expected) {
      const readLen = Math.min(chunkSize, expected - offset);
      const chunk = await reader.readChunk(offset, readLen);
      if (chunk.length === 0) break;
      out.set(chunk, offset);
      offset += chunk.length;
    }

    const exact = toExactArrayBuffer(out);
    const ok = accept(exact);
    if (ok) return ok;

    throw new Error(
      `Could not read ${expected} exact bytes from the selected file (got a short/long read).`
    );
  } finally {
    await reader.close();
  }
}
