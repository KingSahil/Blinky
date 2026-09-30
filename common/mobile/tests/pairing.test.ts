import { expect, test } from 'bun:test';
import { parsePairingQr } from '../lib/pairing';

const FULL = JSON.stringify({
  v: 1,
  ip: '192.168.1.15',
  ws: 9001,
  disc: 9004,
  token: 'abc123token',
  pin: null,
  mode: 'development',
});

test('parses a full PC pairing QR payload', () => {
  const parsed = parsePairingQr(FULL);
  expect(parsed).not.toBeNull();
  expect(parsed!.ip).toBe('192.168.1.15');
  expect(parsed!.token).toBe('abc123token');
  expect(parsed!.pin).toBeNull();
  expect(parsed!.mode).toBe('development');
  expect(parsed!.ws).toBe(9001);
  expect(parsed!.disc).toBe(9004);
});

test('parses release payload with certificate pin', () => {
  const parsed = parsePairingQr(JSON.stringify({
    v: 1, ip: '100.122.62.2', token: 'tok', pin: 'sha256/xyz', mode: 'release',
  }));
  expect(parsed!.ip).toBe('100.122.62.2');
  expect(parsed!.pin).toBe('sha256/xyz');
});

test('applies defaults for missing optional fields', () => {
  const parsed = parsePairingQr(JSON.stringify({ ip: '10.0.0.5' }));
  expect(parsed!.v).toBe(1);
  expect(parsed!.ws).toBe(9001);
  expect(parsed!.disc).toBe(9004);
  expect(parsed!.token).toBeUndefined();
  expect(parsed!.pin).toBeNull();
});

test('accepts blinky:// scheme wrappers', () => {
  expect(parsePairingQr(`blinky://connect/${encodeURIComponent(FULL)}`)!.ip).toBe('192.168.1.15');
  expect(parsePairingQr(`blinky://pair#${encodeURIComponent(FULL)}`)!.ip).toBe('192.168.1.15');
});

test('rejects non-pairing codes', () => {
  expect(parsePairingQr('https://example.com')).toBeNull();
  expect(parsePairingQr('WIFI:S:home;T:WPA;P:secret;;')).toBeNull();
  expect(parsePairingQr('not json at all')).toBeNull();
  expect(parsePairingQr(JSON.stringify({ foo: 'bar' }))).toBeNull();
  expect(parsePairingQr(JSON.stringify({ ip: '' }))).toBeNull();
  expect(parsePairingQr(JSON.stringify(['192.168.1.1']))).toBeNull();
});
