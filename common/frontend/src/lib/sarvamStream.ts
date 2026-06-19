export class SarvamSpeechToTextStream {
  private ws: WebSocket | null = null;
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
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  get isClosedOrClosing(): boolean {
    return this.ws === null || this.ws.readyState === WebSocket.CLOSED || this.ws.readyState === WebSocket.CLOSING;
  }

  connect() {
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
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.sendStartFrame();
    } else {
      console.log("SarvamSTT: startSession called while connecting. Queueing session start.");
      this.sessionNeedsStart = true;
    }
  }

  private sendStartFrame() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log("SarvamSTT: Sending start frame...");
      const initFrame = {
        action: "start",
        model: "saaras:v3",
        language_code: "en-IN",
        encoding: "LINEAR16",
        sample_rate: 16000
      };
      this.ws.send(JSON.stringify(initFrame));
    }
  }

  disconnect() {
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
}

export class SarvamTextToSpeechStream {
  private ws: WebSocket | null = null;
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
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  get isClosedOrClosing(): boolean {
    return this.ws === null || this.ws.readyState === WebSocket.CLOSED || this.ws.readyState === WebSocket.CLOSING;
  }

  connect() {
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
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        text,
        model: "bulbul:v3",
        target_language_code: "en-IN",
        speaker: "ratan",
        pace: 1.05,
        output_audio_codec: "pcm",
        speech_sample_rate: 16000
      }));
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
