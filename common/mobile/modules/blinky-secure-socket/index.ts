import { requireOptionalNativeModule, type EventSubscription } from 'expo-modules-core';

type NativeSecureSocketFunctions = {
  connect(id: string, url: string, pin: string): Promise<void>;
  sendText(id: string, data: string): Promise<void>;
  sendBinary(id: string, base64Data: string): Promise<void>;
  close(id: string): Promise<void>;
  getSecureValue(key: string): Promise<string | null>;
  setSecureValue(key: string, value: string): Promise<void>;
  deleteSecureValue(key: string): Promise<void>;
  hashFile(uri: string): Promise<{ size: number; sha256: string }>;
  uploadFile(options: {
    sourceUri: string;
    transferId: string;
    url: string;
    token: string;
    pin?: string;
    size: number;
    chunkSize: number;
    offset: number;
  }): Promise<{ transferId: string; uploadOffset: number; complete: boolean }>;
  downloadFile(options: {
    transferId: string;
    url: string;
    token: string;
    pin?: string;
    size: number;
    sha256: string;
    filename: string;
  }): Promise<string>;
};

export type SecureSocketEvent = {
  id: string;
  data?: string;
  error?: string;
  direction?: 'upload' | 'download';
  bytes?: number;
  total?: number;
};

export type SecureSocketEventName = 'onOpen' | 'onMessage' | 'onClose' | 'onError' | 'onTransferProgress';

type NativeSecureSocketModule = NativeSecureSocketFunctions & {
  addListener<EventName extends SecureSocketEventName>(
    eventName: EventName,
    listener: (event: SecureSocketEvent) => void,
  ): EventSubscription;
};

const NativeModule = requireOptionalNativeModule<NativeSecureSocketModule>('BlinkySecureSocket');

export const isNative = Boolean(NativeModule);
export const isAvailable = true;

const fallbackListeners = new Map<SecureSocketEventName, Set<(event: SecureSocketEvent) => void>>();

function emitFallbackEvent(name: SecureSocketEventName, event: SecureSocketEvent) {
  const listeners = fallbackListeners.get(name);
  if (listeners) {
    for (const listener of listeners) {
      try {
        listener(event);
      } catch {}
    }
  }
}

// Pure JS SHA-256 for environments where native crypto / TurboModules are absent
function sha256Pure(bytes: Uint8Array): string {
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a;
  let h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;

  const len = bytes.length;
  const bitLenHi = Math.floor(len / 0x20000000);
  const bitLenLo = (len * 8) >>> 0;

  const padLen = (len % 64 < 56) ? (56 - (len % 64)) : (120 - (len % 64));
  const totalLen = len + padLen + 8;
  const padded = new Uint8Array(totalLen);
  padded.set(bytes, 0);
  padded[len] = 0x80;

  const view = new DataView(padded.buffer, padded.byteOffset, padded.byteLength);
  view.setUint32(totalLen - 8, bitLenHi, false);
  view.setUint32(totalLen - 4, bitLenLo, false);

  const w = new Uint32Array(64);
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));

  for (let i = 0; i < totalLen; i += 64) {
    for (let t = 0; t < 16; t++) {
      w[t] = view.getUint32(i + t * 4, false);
    }
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      const s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (((w[t - 16] + s0) >>> 0) + ((w[t - 7] + s1) >>> 0)) >>> 0;
    }

    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;

    for (let t = 0; t < 64; t++) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ ((~e) & g);
      const temp1 = (((h + s1) >>> 0) + (((ch + K[t]) >>> 0) + w[t]) >>> 0) >>> 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
    h5 = (h5 + f) >>> 0;
    h6 = (h6 + g) >>> 0;
    h7 = (h7 + h) >>> 0;
  }

  const toHex = (n: number) => (n >>> 0).toString(16).padStart(8, '0');
  return toHex(h0) + toHex(h1) + toHex(h2) + toHex(h3) + toHex(h4) + toHex(h5) + toHex(h6) + toHex(h7);
}

async function computeSha256(buffer: ArrayBuffer): Promise<string> {
  if (typeof globalThis.crypto?.subtle?.digest === 'function') {
    try {
      const hashBuffer = await globalThis.crypto.subtle.digest('SHA-256', buffer);
      return Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
    } catch {}
  }
  return sha256Pure(new Uint8Array(buffer));
}

async function readUriAsArrayBuffer(uri: string): Promise<ArrayBuffer> {
  // Method 1: React Native fetch() handles content:// and file:// natively
  try {
    const res = await fetch(uri);
    const blob = await res.blob();
    if (blob && typeof blob.size === 'number' && blob.size > 0) {
      return await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as ArrayBuffer);
        reader.onerror = () => reject(reader.error || new Error('Failed to read file content'));
        reader.readAsArrayBuffer(blob);
      });
    }
  } catch {}

  // Method 2: Modern expo-file-system File class
  try {
    const { File } = require('expo-file-system');
    if (typeof File === 'function') {
      const file = new File(uri);
      const bytes = await file.bytes();
      if (bytes && bytes.length > 0) {
        return bytes.buffer;
      }
    }
  } catch {}

  // Method 3: expo-file-system/legacy
  try {
    const FileSystem = require('expo-file-system/legacy');
    if (FileSystem?.readAsStringAsync) {
      const b64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType?.Base64 || 'base64',
      });
      const binaryStr = atob(b64);
      const len = binaryStr.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      return bytes.buffer;
    }
  } catch {}

  throw new Error('Unable to read selected file on this device.');
}

function getNative(): NativeSecureSocketModule {
  if (!NativeModule) {
    throw new Error("Cannot find native module 'BlinkySecureSocket'. It is not available in Expo Go; please use the installed Blinky APK or development build.");
  }
  return NativeModule;
}

export const connect = (id: string, url: string, pin: string) => getNative().connect(id, url, pin);
export const sendText = (id: string, data: string) => getNative().sendText(id, data);
export const sendBinary = (id: string, base64Data: string) => getNative().sendBinary(id, base64Data);
export const close = (id: string) => getNative().close(id);
export const getSecureValue = (key: string) => getNative().getSecureValue(key);
export const setSecureValue = (key: string, value: string) => getNative().setSecureValue(key, value);
export const deleteSecureValue = (key: string) => getNative().deleteSecureValue(key);

export const hashFile = async (uri: string): Promise<{ size: number; sha256: string }> => {
  if (NativeModule) {
    return NativeModule.hashFile(uri);
  }
  const buffer = await readUriAsArrayBuffer(uri);
  const digest = await computeSha256(buffer);
  return {
    size: buffer.byteLength,
    sha256: digest,
  };
};

export const uploadFile = async (
  options: Parameters<NativeSecureSocketFunctions['uploadFile']>[0]
): Promise<{ transferId: string; uploadOffset: number; complete: boolean }> => {
  if (NativeModule) {
    return NativeModule.uploadFile(options);
  }

  const buffer = await readUriAsArrayBuffer(options.sourceUri);
  const totalSize = buffer.byteLength;
  let offset = options.offset || 0;
  const chunkSize = options.chunkSize || 16 * 1024 * 1024;

  while (offset < totalSize) {
    const nextEnd = Math.min(offset + chunkSize, totalSize);
    const chunk = buffer.slice(offset, nextEnd);

    const uploadRes = await fetch(options.url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${options.token}`,
        'Upload-Offset': String(offset),
        'Content-Length': String(chunk.byteLength),
        'Content-Type': 'application/octet-stream',
      },
      body: chunk,
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

    emitFallbackEvent('onTransferProgress', {
      id: options.transferId,
      direction: 'upload',
      bytes: offset,
      total: totalSize,
    });
  }

  return {
    transferId: options.transferId,
    uploadOffset: offset,
    complete: true,
  };
};

export const downloadFile = async (
  options: Parameters<NativeSecureSocketFunctions['downloadFile']>[0]
): Promise<string> => {
  if (NativeModule) {
    return NativeModule.downloadFile(options);
  }

  const safeFilename = (options.filename || 'blinky-download.bin').replace(/[\\/:*?"<>|\x00-\x1F]/g, '_');

  // Method 1: Modern expo-file-system File & Directory API
  try {
    const { File, Paths, Directory } = require('expo-file-system');
    if (typeof File?.downloadFileAsync === 'function' && Paths?.document) {
      const destDir = new Directory(Paths.document, 'BlinkyTransfers');
      if (!destDir.exists) {
        destDir.create();
      }
      const destFile = new File(destDir, safeFilename);
      const downloaded = await File.downloadFileAsync(options.url, destFile, {
        headers: {
          'Authorization': `Bearer ${options.token}`,
        },
        idempotent: true,
      });

      emitFallbackEvent('onTransferProgress', {
        id: options.transferId,
        direction: 'download',
        bytes: options.size,
        total: options.size,
      });

      return downloaded.uri;
    }
  } catch {}

  // Method 2: expo-file-system/legacy
  try {
    const FileSystem = require('expo-file-system/legacy');
    if (FileSystem?.documentDirectory && typeof FileSystem.downloadAsync === 'function') {
      const targetDir = `${FileSystem.documentDirectory}BlinkyTransfers/`;
      const dirInfo = await FileSystem.getInfoAsync(targetDir).catch(() => ({ exists: false }));
      if (!dirInfo.exists) {
        await FileSystem.makeDirectoryAsync(targetDir, { intermediates: true }).catch(() => {});
      }
      const targetUri = `${targetDir}${safeFilename}`;
      const downloadResult = await FileSystem.downloadAsync(options.url, targetUri, {
        headers: {
          'Authorization': `Bearer ${options.token}`,
        },
      });

      emitFallbackEvent('onTransferProgress', {
        id: options.transferId,
        direction: 'download',
        bytes: options.size,
        total: options.size,
      });

      return downloadResult.uri;
    }
  } catch {}

  // Method 3: Standard fetch blob URL
  const res = await fetch(options.url, {
    headers: {
      'Authorization': `Bearer ${options.token}`,
    },
  });
  if (!res.ok) {
    throw new Error(`Download failed with status ${res.status}`);
  }
  const blob = await res.blob();
  emitFallbackEvent('onTransferProgress', {
    id: options.transferId,
    direction: 'download',
    bytes: options.size,
    total: options.size,
  });
  return URL.createObjectURL(blob);
};

export function addListener(
  name: SecureSocketEventName,
  listener: (event: SecureSocketEvent) => void,
): EventSubscription {
  if (NativeModule) {
    return NativeModule.addListener(name, listener);
  }

  if (!fallbackListeners.has(name)) {
    fallbackListeners.set(name, new Set());
  }
  fallbackListeners.get(name)!.add(listener);

  return {
    remove: () => {
      fallbackListeners.get(name)?.delete(listener);
    },
  };
}
