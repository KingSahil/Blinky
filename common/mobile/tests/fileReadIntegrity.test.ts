import { describe, expect, test } from 'bun:test';
import { toExactArrayBuffer, acceptReadBuffer } from '../lib/fileBytes';

describe('toExactArrayBuffer (transfer read integrity)', () => {
  test('strips pooled-buffer garbage around a view', () => {
    // Simulate expo-file-system returning a view into a larger pooled buffer.
    const pool = new Uint8Array([9, 9, 9, 1, 2, 3, 4, 9, 9, 9]);
    const view = pool.subarray(3, 7);
    const exact = toExactArrayBuffer(view);
    expect(exact.byteLength).toBe(4);
    expect(Array.from(new Uint8Array(exact))).toEqual([1, 2, 3, 4]);
  });

  test('passes through an exactly-backed buffer untouched', () => {
    const bytes = new Uint8Array([0xff, 0xd8, 0xff, 0xe0]);
    const exact = toExactArrayBuffer(bytes);
    expect(exact.byteLength).toBe(4);
    expect(new Uint8Array(exact)[0]).toBe(0xff);
  });

  test('jpeg magic bytes survive the copy', () => {
    const pool = new Uint8Array(64);
    pool.set([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10], 10);
    const view = pool.subarray(10, 16);
    const exact = new Uint8Array(toExactArrayBuffer(view));
    expect(Array.from(exact)).toEqual([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);
  });

  test('acceptReadBuffer rejects empty and size-mismatched reads', () => {
    expect(acceptReadBuffer(null, 10)).toBeNull();
    expect(acceptReadBuffer(new ArrayBuffer(0), 0)).toBeNull();
    expect(acceptReadBuffer(new ArrayBuffer(8), 10)).toBeNull();
    expect(acceptReadBuffer(new ArrayBuffer(12), 10)).toBeNull();
    const good = new ArrayBuffer(10);
    expect(acceptReadBuffer(good, 10)).toBe(good);
    expect(acceptReadBuffer(good, null)).toBe(good);
  });
});
