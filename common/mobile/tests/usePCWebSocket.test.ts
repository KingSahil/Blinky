import { afterEach, beforeEach, expect, mock, test } from 'bun:test';

// Exercise the real hook with deterministic React state and native events.
// This does not emulate React Native rendering or a physical TLS handshake.
let slots: any[] = [];
let cursor = 0;
let cleanup: (() => void) | undefined;
const listeners = new Map<string, Set<(event: any) => void>>();
const timers = new Map<number, () => void>();
let timerId = 0;
const realSetTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;
const originalMode = process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE;
process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE = 'release';

mock.module('react', () => ({
  useState(initial: any) {
    const index = cursor++;
    if (!(index in slots)) slots[index] = initial;
    return [slots[index], (value: any) => { slots[index] = value; }];
  },
  useRef(initial: any) {
    const index = cursor++;
    return slots[index] ??= { current: initial };
  },
  useCallback: (callback: any) => callback,
  useEffect(effect: () => () => void) { cleanup ??= effect(); },
}));

const connectNative = mock(async (_id: string, _url: string, _pin: string) => {});
const sendText = mock(async (_id: string, _data: string) => {});
const close = mock(async (_id: string) => {});
mock.module('../modules/blinky-secure-socket', () => ({
  connect: connectNative, sendText, close,
  addListener(name: string, callback: (event: any) => void) {
    if (!listeners.has(name)) listeners.set(name, new Set());
    listeners.get(name)!.add(callback);
    return { remove: () => listeners.get(name)!.delete(callback) };
  },
}));
const { usePCWebSocket } = await import('../usePCWebSocket');
function render() { cursor = 0; return usePCWebSocket(); }
function emit(name: string, id: string, payload = {}) {
  for (const callback of [...(listeners.get(name) || [])]) callback({ id, ...payload });
}
function start() {
  render().connect('192.168.0.105', 'test-token', 'sha256/test-pin');
  return connectNative.mock.calls.at(-1)![0];
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

beforeEach(() => {
  slots = []; cursor = 0; cleanup = undefined; listeners.clear(); timers.clear();
  connectNative.mockReset(); sendText.mockReset(); close.mockReset();
  connectNative.mockImplementation(async () => {});
  sendText.mockImplementation(async () => {});
  close.mockImplementation(async () => {});
  globalThis.setTimeout = ((callback: () => void) => {
    timers.set(++timerId, callback); return timerId;
  }) as any;
  globalThis.clearTimeout = ((id: number) => timers.delete(id)) as any;
});
afterEach(() => {
  cleanup?.();
  globalThis.setTimeout = realSetTimeout;
  globalThis.clearTimeout = realClearTimeout;
});

test('wrong token keeps an error after listeners and socket are cleaned up', () => {
  const id = start(); emit('onOpen', id);
  emit('onMessage', id, { data: JSON.stringify({ type: 'auth_result', ok: false }) });
  emit('onClose', id);
  expect(render().status).toBe('error');
  expect(render().errorMsg).toBe('The PC rejected the remote token.');
  expect(close).toHaveBeenCalledWith(id);
  expect([...listeners.values()].every(set => set.size === 0)).toBe(true);
});

test('commands and queries wait for a strict positive authentication acknowledgement', () => {
  const id = start(); emit('onOpen', id);
  expect(render().sendCommand('volume_up')).toBe(false);
  expect(render().sendQuery('hello', 'q1')).toBe(false);
  expect(render().status).toBe('connecting');
  emit('onMessage', id, { data: JSON.stringify({ type: 'auth_result', ok: true }) });
  expect(render().status).toBe('connected');
  expect(render().sendQuery('hello', 'q1')).toBe(true);
  expect(sendText).toHaveBeenLastCalledWith(id, JSON.stringify({ requestId: 'q1', query: 'hello' }));
  emit('onMessage', id, { data: JSON.stringify({ requestId: 'q1', status: 'success' }) });
  expect(render().latestResponse).toEqual({ requestId: 'q1', status: 'success' });
});

test('a string auth acknowledgement does not authenticate', () => {
  const id = start(); emit('onOpen', id);
  emit('onMessage', id, { data: JSON.stringify({ type: 'auth_result', ok: 'false' }) });
  expect(render().status).toBe('error');
});

test('timeout remains active until authentication completes', () => {
  const id = start(); emit('onOpen', id);
  expect(timers.size).toBe(1);
  for (const callback of [...timers.values()]) callback();
  expect(render().status).toBe('error');
  expect(render().errorMsg).toContain('timed out');
  expect(close).toHaveBeenCalledWith(id);
});

test('late connect failure cannot overwrite a newer authenticated connection', async () => {
  let reject!: (error: Error) => void;
  connectNative.mockImplementationOnce(() => new Promise<void>((_, fail) => { reject = fail; }));
  start();
  const newer = start(); emit('onOpen', newer);
  emit('onMessage', newer, { data: JSON.stringify({ type: 'auth_result', ok: true }) });
  reject(new Error('old connection failed')); await flush();
  expect(render().status).toBe('connected');
  expect(render().errorMsg).toBeNull();
});

test('late auth-send failure cannot disconnect a newer connection', async () => {
  let reject!: (error: Error) => void;
  sendText.mockImplementationOnce(() => new Promise<void>((_, fail) => { reject = fail; }));
  const old = start(); emit('onOpen', old);
  const newer = start(); emit('onOpen', newer);
  emit('onMessage', newer, { data: JSON.stringify({ type: 'auth_result', ok: true }) });
  reject(new Error('old send failed')); await flush();
  expect(render().status).toBe('connected');
  expect(close.mock.calls.some(([id]) => id === newer)).toBe(false);
});

test('closing before authentication produces a useful error', () => {
  const id = start(); emit('onOpen', id); emit('onClose', id);
  expect(render().status).toBe('error');
  expect(render().errorMsg).toContain('authentication');
});

test('failed authenticated send reports an error and disconnects', async () => {
  const id = start(); emit('onOpen', id);
  emit('onMessage', id, { data: JSON.stringify({ type: 'auth_result', ok: true }) });
  sendText.mockRejectedValueOnce(new Error('send queue closed'));
  expect(render().sendCommand('volume_up')).toBe(true);
  await flush();
  expect(render().status).toBe('error');
  expect(render().errorMsg).toBe('send queue closed');
  expect(close).toHaveBeenCalledWith(id);
});

test('restoring credentials reconnects after a failed token attempt', () => {
  const first = start(); emit('onOpen', first);
  emit('onMessage', first, { data: JSON.stringify({ type: 'auth_result', ok: false }) });
  const second = start(); emit('onOpen', second);
  emit('onMessage', second, { data: JSON.stringify({ type: 'auth_result', ok: true }) });
  expect(render().status).toBe('connected');
  expect(render().errorMsg).toBeNull();
  expect(timers.size).toBe(0);
});

test('disconnect clears pending timeout and unmount closes the socket', () => {
  start(); render().disconnect(); expect(timers.size).toBe(0);
  const id = start(); cleanup?.();
  expect(close).toHaveBeenCalledWith(id);
  expect(timers.size).toBe(0);
});

// The mode is captured on module import; restore the process for other tests.
if (originalMode === undefined) delete process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE;
else process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE = originalMode;
