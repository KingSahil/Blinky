import { afterEach, beforeEach, expect, mock, test } from 'bun:test';

const oldMode = process.env.VITE_BLINKY_TRANSPORT_MODE;
process.env.VITE_BLINKY_TRANSPORT_MODE = 'release';
const previousWindow = globalThis.window;
(globalThis as any).window = { __TAURI_INTERNALS__: {} };
let handler: (event: any) => void;
const unlisten = mock(() => {});
const listen = mock(async (callback: typeof handler) => { handler = callback; return unlisten; });
const info = mock(async () => ({ certificate_pin: 'sha256/test' }));
const connect = mock(async (_id: string, _url: string, _pin: string) => {});
const close = mock(async (_id: string) => {});
const sendBinary = mock(async (_id: string, _data: ArrayBuffer) => {});
const sendText = mock(async (_id: string, _data: string) => {});
mock.module('../src/lib/tauri', () => ({
  listenForSecureSocketEvents: listen, getSecureTransportInfo: info,
  connectSecureSocket: connect, closeSecureSocket: close,
  sendSecureSocketBinary: sendBinary, sendSecureSocketText: sendText,
}));
const { SarvamSpeechToTextStream, SarvamTextToSpeechStream } = await import('../src/lib/sarvamStream');
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
let stream: SarvamSpeechToTextStream | SarvamTextToSpeechStream;

beforeEach(() => {
  for (const fn of [unlisten, listen, info, connect, close, sendBinary, sendText]) fn.mockClear();
  info.mockImplementation(async () => ({ certificate_pin: 'sha256/test' }));
  connect.mockImplementation(async () => {});
});
afterEach(() => stream?.disconnect());

for (const kind of ['stt', 'tts'] as const) {
  const create = (onError = mock(() => {})) => kind === 'stt'
    ? new SarvamSpeechToTextStream('', () => {}, onError)
    : new SarvamTextToSpeechStream('', () => {}, onError);

  test(`${kind}: disconnect during listener setup never starts a connection`, async () => {
    stream = create(); stream.connect(); stream.disconnect(); await flush();
    expect(connect).not.toHaveBeenCalled();
    expect(unlisten).toHaveBeenCalledTimes(1);
  });

  test(`${kind}: disconnect during identity lookup never starts a connection`, async () => {
    let resolve!: (value: { certificate_pin: string }) => void;
    info.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    stream = create(); stream.connect(); await flush(); stream.disconnect();
    resolve({ certificate_pin: 'sha256/test' }); await flush();
    expect(connect).not.toHaveBeenCalled();
  });

  test(`${kind}: a socket completing after disconnect is closed again`, async () => {
    let resolve!: () => void;
    connect.mockImplementationOnce(() => new Promise<void>(done => { resolve = done; }));
    stream = create(); stream.connect(); await flush();
    const id = connect.mock.calls[0][0]; stream.disconnect(); resolve(); await flush();
    expect(close.mock.calls.filter(([socketId]) => socketId === id)).toHaveLength(2);
  });

  test(`${kind}: connection failure removes listeners and reports the error`, async () => {
    connect.mockRejectedValueOnce(new Error('TLS failed'));
    const onError = mock(() => {});
    stream = create(onError); stream.connect(); await flush();
    expect(unlisten).toHaveBeenCalled();
    expect(onError).toHaveBeenCalled();
    expect(stream.isClosedOrClosing).toBe(true);
  });
}

test('STT preserves queued start and audio until the native WSS open event', async () => {
  const stt = new SarvamSpeechToTextStream('', () => {}, () => {}); stream = stt;
  stt.connect(); stt.startSession();
  expect(stt.isClosedOrClosing).toBe(false);
  const audio = new ArrayBuffer(8); stt.sendAudioChunk(audio); await flush();
  const id = connect.mock.calls[0][0];
  expect(connect.mock.calls[0][1]).toBe('wss://127.0.0.1:9001/sarvam-stt');
  handler({ socket_id: id, kind: 'open' });
  expect(sendText).toHaveBeenCalled();
  expect(sendBinary).toHaveBeenCalledWith(id, audio);
  expect(stt.isConnected).toBe(true);
});

// Restore global values after all tests in this file.
import { afterAll } from 'bun:test';
afterAll(() => {
  if (oldMode === undefined) delete process.env.VITE_BLINKY_TRANSPORT_MODE;
  else process.env.VITE_BLINKY_TRANSPORT_MODE = oldMode;
  (globalThis as any).window = previousWindow;
});
