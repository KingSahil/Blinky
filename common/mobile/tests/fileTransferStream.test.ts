import { describe, expect, test } from 'bun:test';
import { createHash, randomBytes } from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import {
  base64ToUint8Array,
  uint8ArrayToBase64,
  getFileSize,
  readChunkAsUint8Array,
  hashFileStreaming,
  uploadFileStreaming,
  readUriAsArrayBufferStreaming,
} from '../lib/fileTransferStream';

describe('fileTransferStream', () => {
  test('base64ToUint8Array / uint8ArrayToBase64 roundtrip', () => {
    const original = new Uint8Array([0, 1, 2, 253, 254, 255, 42, 99, 128]);
    const b64 = uint8ArrayToBase64(original);
    const decoded = base64ToUint8Array(b64);
    expect(Array.from(decoded)).toEqual(Array.from(original));
  });

  test('getFileSize and readChunkAsUint8Array read arbitrary ranges', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'blinky-test-'));
    const testFile = path.join(tempDir, 'test_range.bin');
    const data = randomBytes(1024 * 1024); // 1 MB
    fs.writeFileSync(testFile, data);

    try {
      const size = await getFileSize(testFile);
      expect(size).toBe(1024 * 1024);

      // Read middle chunk
      const chunk = await readChunkAsUint8Array(testFile, 500, 100);
      expect(chunk.length).toBe(100);
      expect(Array.from(chunk)).toEqual(Array.from(data.subarray(500, 600)));

      // Read trailing chunk
      const tail = await readChunkAsUint8Array(testFile, 1024 * 1024 - 50, 50);
      expect(tail.length).toBe(50);
      expect(Array.from(tail)).toEqual(Array.from(data.subarray(1024 * 1024 - 50)));
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  test('hashFileStreaming matches node crypto on multi-megabyte files with small chunks', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'blinky-test-'));
    const testFile = path.join(tempDir, 'test_large.bin');
    // Create 5 MB file
    const data = randomBytes(5 * 1024 * 1024);
    fs.writeFileSync(testFile, data);

    try {
      const expectedSha256 = createHash('sha256').update(data).digest('hex');

      // Test with small 64 KB chunk size to force multiple iterations
      const result = await hashFileStreaming(testFile, 64 * 1024);
      expect(result.size).toBe(5 * 1024 * 1024);
      expect(result.sha256).toBe(expectedSha256);
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  test('hashFileStreaming handles empty file', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'blinky-test-'));
    const testFile = path.join(tempDir, 'empty.bin');
    fs.writeFileSync(testFile, new Uint8Array(0));

    try {
      const expectedSha256 = createHash('sha256').update(new Uint8Array(0)).digest('hex');
      const result = await hashFileStreaming(testFile);
      expect(result.size).toBe(0);
      expect(result.sha256).toBe(expectedSha256);
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  test('uploadFileStreaming sends chunks and reports progress', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'blinky-test-'));
    const testFile = path.join(tempDir, 'test_upload.bin');
    const totalBytes = 250 * 1024; // 250 KB
    const data = randomBytes(totalBytes);
    fs.writeFileSync(testFile, data);

    // Mock upload server
    const uploadedChunks: { offset: number; length: number; data: Buffer }[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(req) {
        const url = new URL(req.url);
        if (url.pathname.startsWith('/upload/')) {
          const auth = req.headers.get('authorization');
          expect(auth).toBe('Bearer test-token');
          const offset = parseInt(req.headers.get('upload-offset') || '0', 10);
          const arrayBuffer = await req.arrayBuffer();
          const chunkBuf = Buffer.from(arrayBuffer);
          uploadedChunks.push({
            offset,
            length: chunkBuf.length,
            data: chunkBuf,
          });
          const nextOffset = offset + chunkBuf.length;
          return new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: {
              'Upload-Offset': String(nextOffset),
              'Content-Type': 'application/json',
            },
          });
        }
        return new Response('Not found', { status: 404 });
      },
    });

    try {
      const progressEvents: number[] = [];
      const result = await uploadFileStreaming(
        {
          sourceUri: testFile,
          transferId: 'test-transfer-123',
          url: `http://localhost:${server.port}/upload/test-transfer-123`,
          token: 'test-token',
          size: totalBytes,
          chunkSize: 64 * 1024, // 64 KB chunks
          offset: 0,
        },
        (progress) => {
          progressEvents.push(progress.bytes);
        }
      );

      expect(result.complete).toBe(true);
      expect(result.uploadOffset).toBe(totalBytes);
      expect(progressEvents.length).toBeGreaterThanOrEqual(4);
      expect(progressEvents[progressEvents.length - 1]).toBe(totalBytes);

      // Verify concatenated chunks match original data
      const reassembled = Buffer.concat(uploadedChunks.map((c) => c.data));
      expect(reassembled.length).toBe(totalBytes);
      expect(reassembled.equals(data)).toBe(true);
    } finally {
      server.stop(true);
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });

  test('readUriAsArrayBufferStreaming safely reads file into ArrayBuffer', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'blinky-test-'));
    const testFile = path.join(tempDir, 'test_read_buf.bin');
    const data = randomBytes(500 * 1024); // 500 KB
    fs.writeFileSync(testFile, data);

    try {
      const buf = await readUriAsArrayBufferStreaming(testFile);
      expect(buf.byteLength).toBe(500 * 1024);
      const readBytes = Buffer.from(buf);
      expect(readBytes.equals(data)).toBe(true);
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });
});
