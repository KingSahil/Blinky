import { expect, test } from 'bun:test';
import { createHash } from 'crypto';
import { StreamingSha256 } from '../lib/streamingSha256';

test('StreamingSha256 matches native crypto for empty string', () => {
  const hasher = new StreamingSha256();
  expect(hasher.digest()).toBe(createHash('sha256').digest('hex'));
});

test('StreamingSha256 matches native crypto for standard text', () => {
  const text = 'Hello, world! Testing Blinky StreamingSha256 on mobile file transfer.';
  const data = new TextEncoder().encode(text);
  const hasher = new StreamingSha256();
  hasher.update(data);
  expect(hasher.digest()).toBe(createHash('sha256').update(data).digest('hex'));
});

test('StreamingSha256 matches native crypto when fed in arbitrary chunks', () => {
  const buffer = new Uint8Array(256 * 1024); // 256 KB
  for (let i = 0; i < buffer.length; i++) {
    buffer[i] = (i * 31 + 17) & 0xff;
  }
  const expectedHash = createHash('sha256').update(buffer).digest('hex');

  // Test various chunk sizes
  for (const chunkSize of [1, 7, 63, 64, 65, 1024, 7777, 65536]) {
    const hasher = new StreamingSha256();
    for (let offset = 0; offset < buffer.length; offset += chunkSize) {
      hasher.update(buffer.subarray(offset, Math.min(offset + chunkSize, buffer.length)));
    }
    expect(hasher.digest()).toBe(expectedHash);
  }
});
