import {
  closeSecureSocket,
  connectSecureSocket,
  getSecureTransportInfo,
  listenForSecureSocketEvents,
  sendSecureSocketBinary,
  sendSecureSocketText,
  type SecureSocketEvent,
} from './tauri';

function shouldUseNativeSecureTransport(): boolean {
  return import.meta.env.VITE_BLINKY_TRANSPORT_MODE === 'release'
    && typeof window !== 'undefined'
    && Boolean((window as any).__TAURI_INTERNALS__);
}

function releaseGatewayUrl(path: string, configuredUrl: string | undefined): string {
  const url = configuredUrl || `wss://127.0.0.1:9001${path}`;
  if (!url.startsWith('wss://')) {
    throw new Error(`Release transport requires a wss:// Sarvam gateway URL, got ${url}`);
  }
  return url;
}

export class SarvamSpeechToTextStream {
  private ws: WebSocket | null = null;
  private nativeSocketId: string | null = null;
  private nativeUnlisten: (() => void) | null = null;
  private nativeOpen = false;
  private onTranscript: (text: string, isFinal: boolean) => void;
  private onError: (err: any) => void;
  private sessionNeedsStart = false;
  private queuedChunks: ArrayBuffer[] = [];

  constructor(
    public apiKey: string,
    onTranscript: (text: string, isFinal: boolean) => void,
    onError: (err: any) => void
  ) {
    this.onTranscript = onTranscript;
    this.onError = onError;
  }

  get isConnected(): boolean {
    return this.nativeOpen || (this.ws !== null && this.ws.readyState === WebSocket.OPEN);
  }

  get isClosedOrClosing(): boolean {
    return this.nativeSocketId === null
      ? this.ws === null || this.ws.readyState === WebSocket.CLOSED || this.ws.readyState === WebSocket.CLOSING
      : false;
  }

  connect() {
    this.disconnect();
    if (shouldUseNativeSecureTransport()) {
      this.connectNative();
      return;
    }

    const url = import.meta.env.VITE_SARVAM_GATEWAY_STT_URL || 'ws://127.0.0.1:9001/sarvam-stt';
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log("SarvamSTT: WebSocket connection opened.");
      if (this.sessionNeedsStart) {
        this.sendStartFrame();
        this.sessionNeedsStart = false;
      }
      if (this.queuedChunks.length > 0) {
        console.log(`SarvamSTT: Flushing ${this.queuedChunks.length} queued audio chunks.`);
        while (this.queuedChunks.length > 0) {
          const chunk = this.queuedChunks.shift();
          if (chunk) {
            this.ws?.send(chunk);
          }
        }
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.transcript) {
          this.onTranscript(payload.transcript, !!payload.is_final);
        }
      } catch (err) {
        this.onError(err);
      }
    };

    this.ws.onerror = (event) => this.onError(event);
    this.ws.onclose = () => {
      console.log("SarvamSTT: WebSocket connection closed.");
      this.ws = null;
    };
  }

  sendAudioChunk(chunk: ArrayBuffer) {
    if (this.nativeSocketId) {
      if (this.nativeOpen) {
        void sendSecureSocketBinary(this.nativeSocketId, chunk).catch(this.onError);
      } else {
        this.queuedChunks.push(chunk);
      }
      return;
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(chunk);
    } else if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
      console.log("SarvamSTT: Connection is connecting. Queueing audio chunk.");
      this.queuedChunks.push(chunk);
    } else {
      console.warn("SarvamSTT: Cannot send audio chunk, WebSocket is closed or closing.");
    }
  }

  startSession() {
    if (this.isConnected) {
      this.sendStartFrame();
    } else {
      console.log("SarvamSTT: startSession called while connecting. Queueing session start.");
      this.sessionNeedsStart = true;
    }
  }

  private sendStartFrame() {
    if (this.isConnected) {
      console.log("SarvamSTT: Sending start frame...");
      const initFrame = {
        action: "start",
        model: "saaras:v3",
        language_code: "en-IN",
        encoding: "LINEAR16",
        sample_rate: 16000
      };
      this.sendText(JSON.stringify(initFrame));
    }
  }

  disconnect() {
    if (this.nativeSocketId) {
      const socketId = this.nativeSocketId;
      this.nativeUnlisten?.();
      this.nativeUnlisten = null;
      this.nativeSocketId = null;
      this.nativeOpen = false;
      void closeSecureSocket(socketId).catch(() => undefined);
    }
    if (this.ws) {
      if (this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ action: "stop" }));
        } catch {}
      }
      this.ws.close();
      this.ws = null;
    }
    this.sessionNeedsStart = false;
    this.queuedChunks = [];
  }

  private sendText(data: string) {
    if (this.nativeSocketId && this.nativeOpen) {
      void sendSecureSocketText(this.nativeSocketId, data).catch(this.onError);
    } else if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }

  private connectNative() {
    const socketId = `sarvam-stt-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    this.nativeSocketId = socketId;
    const configuredUrl = import.meta.env.VITE_SARVAM_GATEWAY_STT_URL;

    void listenForSecureSocketEvents((event: SecureSocketEvent) => {
      if (event.socket_id !== socketId || this.nativeSocketId !== socketId) return;
      if (event.kind === 'open') {
        this.nativeOpen = true;
        if (this.sessionNeedsStart) {
          this.sendStartFrame();
          this.sessionNeedsStart = false;
        }
        while (this.queuedChunks.length > 0) {
          const chunk = this.queuedChunks.shift();
          if (chunk) this.sendAudioChunk(chunk);
        }
      } else if (event.kind === 'text' && event.data) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.transcript) this.onTranscript(payload.transcript, !!payload.is_final);
        } catch (error) {
          this.onError(error);
        }
      } else if (event.kind === 'close') {
        this.nativeOpen = false;
        this.nativeUnlisten?.();
        this.nativeUnlisten = null;
        this.nativeSocketId = null;
      } else if (event.kind === 'error') {
        this.disconnect();
        this.onError(new Error(event.message || 'Native secure socket error'));
      }
    }).then(async (unlisten) => {
      if (this.nativeSocketId !== socketId) { unlisten(); return; }
      this.nativeUnlisten = unlisten;
      const info = await getSecureTransportInfo();
      if (this.nativeSocketId !== socketId) return;
      const url = releaseGatewayUrl('/sarvam-stt', configuredUrl);
      await connectSecureSocket(socketId, url, info.certificate_pin);
      if (this.nativeSocketId !== socketId) await closeSecureSocket(socketId);
    })
      .catch((error) => {
        if (this.nativeSocketId !== socketId) return;
        this.disconnect();
        this.onError(error);
      });
  }
}

export class SarvamTextToSpeechStream {
  private ws: WebSocket | null = null;
  private nativeSocketId: string | null = null;
  private nativeUnlisten: (() => void) | null = null;
  private nativeOpen = false;
  private onAudioChunk: (base64Data: string) => void;
  private onError: (err: any) => void;

  constructor(
    public apiKey: string,
    onAudioChunk: (base64Data: string) => void,
    onError: (err: any) => void
  ) {
    this.onAudioChunk = onAudioChunk;
    this.onError = onError;
  }

  get isConnected(): boolean {
    return this.nativeOpen || (this.ws !== null && this.ws.readyState === WebSocket.OPEN);
  }

  get isClosedOrClosing(): boolean {
    return this.nativeSocketId === null
      ? this.ws === null || this.ws.readyState === WebSocket.CLOSED || this.ws.readyState === WebSocket.CLOSING
      : false;
  }

  connect() {
    this.disconnect();
    if (shouldUseNativeSecureTransport()) {
      this.connectNative();
      return;
    }

    const url = import.meta.env.VITE_SARVAM_GATEWAY_TTS_URL || 'ws://127.0.0.1:9001/sarvam-tts';
    this.ws = new WebSocket(url);

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.audio) {
          this.onAudioChunk(payload.audio);
        }
      } catch (err) {
        this.onError(err);
      }
    };

    this.ws.onerror = (event) => this.onError(event);
    this.ws.onclose = () => {
      this.ws = null;
    };
  }

  sendText(text: string) {
    const payload = JSON.stringify({
        text,
        model: "bulbul:v3",
        target_language_code: "en-IN",
        speaker: "ratan",
        pace: 1.05,
        output_audio_codec: "pcm",
        speech_sample_rate: 16000
      });
    if (this.nativeSocketId && this.nativeOpen) {
      void sendSecureSocketText(this.nativeSocketId, payload).catch(this.onError);
    } else if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(payload);
    }
  }

  disconnect() {
    if (this.nativeSocketId) {
      const socketId = this.nativeSocketId;
      this.nativeUnlisten?.();
      this.nativeUnlisten = null;
      this.nativeSocketId = null;
      this.nativeOpen = false;
      void closeSecureSocket(socketId).catch(() => undefined);
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private connectNative() {
    const socketId = `sarvam-tts-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    this.nativeSocketId = socketId;
    const configuredUrl = import.meta.env.VITE_SARVAM_GATEWAY_TTS_URL;

    void listenForSecureSocketEvents((event: SecureSocketEvent) => {
      if (event.socket_id !== socketId || this.nativeSocketId !== socketId) return;
      if (event.kind === 'open') {
        this.nativeOpen = true;
      } else if (event.kind === 'text' && event.data) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.audio) this.onAudioChunk(payload.audio);
        } catch (error) {
          this.onError(error);
        }
      } else if (event.kind === 'close') {
        this.nativeOpen = false;
        this.nativeUnlisten?.();
        this.nativeUnlisten = null;
        this.nativeSocketId = null;
      } else if (event.kind === 'error') {
        this.disconnect();
        this.onError(new Error(event.message || 'Native secure socket error'));
      }
    }).then(async (unlisten) => {
      if (this.nativeSocketId !== socketId) { unlisten(); return; }
      this.nativeUnlisten = unlisten;
      const info = await getSecureTransportInfo();
      if (this.nativeSocketId !== socketId) return;
      const url = releaseGatewayUrl('/sarvam-tts', configuredUrl);
      await connectSecureSocket(socketId, url, info.certificate_pin);
      if (this.nativeSocketId !== socketId) await closeSecureSocket(socketId);
    })
      .catch((error) => {
        if (this.nativeSocketId !== socketId) return;
        this.disconnect();
        this.onError(error);
      });
  }
}
