/**
 * AssemblyAI Voice Integration for Blinky AI Desktop Tutor
 * 
 * Supports both hackathon paths:
 * 1. Voice Agent API (End-to-End Voice Agent):
 *    - Universal-3 Pro STT + Turn-Taking + VAD + LLM + Voice Output + JSON-Schema Tool Calling
 * 2. Realtime Speech-to-Text API:
 *    - Universal-3 Pro real-time sub-second streaming transcription over WebSocket
 * 3. REST Audio Transcription Fallback:
 *    - Universal-3 Pro upload & transcript polling
 */

export interface VoiceAgentConfig {
  apiKey: string;
  systemPrompt?: string;
  greeting?: string;
  voice?: string;
  onAgentAudio?: (base64Audio: string) => void;
  onAgentTranscript?: (text: string) => void;
  onUserTranscript?: (text: string, isFinal: boolean) => void;
  onToolCall?: (callId: string, name: string, args: Record<string, any>) => Promise<any> | any;
  onTurnChange?: (turn: 'user' | 'agent' | 'idle') => void;
  onError?: (err: any) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

/**
 * Converts Float32 audio channel samples (-1.0 to 1.0) to 16-bit linear PCM (Int16Array).
 */
export function floatTo16BitPCM(float32Array: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/**
 * Encodes an ArrayBuffer into a base64 string.
 */
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Decodes base64 PCM16 audio and plays it via Web Audio API AudioContext.
 */
export function playPCM16Audio(
  audioCtx: AudioContext,
  pcm16Base64: string,
  sampleRate: number = 24000,
  analyser?: AnalyserNode
): AudioBufferSourceNode {
  const binaryString = atob(pcm16Base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  const int16Array = new Int16Array(bytes.buffer);
  const float32Array = new Float32Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    float32Array[i] = int16Array[i] / 32768;
  }
  const audioBuffer = audioCtx.createBuffer(1, float32Array.length, sampleRate);
  audioBuffer.copyToChannel(float32Array, 0);

  const source = audioCtx.createBufferSource();
  source.buffer = audioBuffer;
  if (analyser) {
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
  } else {
    source.connect(audioCtx.destination);
  }
  source.start();
  return source;
}

/**
 * Path 1: AssemblyAI Voice Agent API
 * Single connection end-to-end voice agent with Universal-3 Pro, VAD, voice output,
 * and JSON-Schema Tool Calling that directly controls the PC desktop.
 */
export class AssemblyAIVoiceAgent {
  private ws: WebSocket | null = null;
  private isConnectedState = false;
  private config: VoiceAgentConfig;
  private pendingTools: Set<string> = new Set();

  constructor(config: VoiceAgentConfig) {
    this.config = config;
  }

  get isConnected(): boolean {
    return this.isConnectedState && this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  connect(preferProxy = true) {
    this.disconnect();

    // Use local Tauri backend proxy (ws://127.0.0.1:9001/assemblyai-agent)
    // which injects the Authorization header, avoiding browser WebSocket header limitations.
    const url = preferProxy
      ? 'ws://127.0.0.1:9001/assemblyai-agent'
      : `wss://agents.assemblyai.com/v1/ws?token=${encodeURIComponent(this.config.apiKey)}`;

    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      this.config.onError?.(e);
      return;
    }

    this.ws.onopen = () => {
      this.isConnectedState = true;
      this.config.onConnect?.();
      this.sendSessionUpdate();
    };

    this.ws.onmessage = async (event) => {
      try {
        let data: any;
        if (typeof event.data === 'string') {
          data = JSON.parse(event.data);
        } else if (event.data instanceof Blob) {
          const text = await event.data.text();
          data = JSON.parse(text);
        } else {
          return;
        }

        this.handleMessage(data);
      } catch (err) {
        console.warn('AssemblyAI Voice Agent: Failed to parse incoming message:', err);
      }
    };

    this.ws.onerror = (err) => {
      console.error('AssemblyAI Voice Agent WebSocket error:', err);
      this.config.onError?.(err);
    };

    this.ws.onclose = () => {
      this.isConnectedState = false;
      this.config.onTurnChange?.('idle');
      this.config.onDisconnect?.();
      this.ws = null;
    };
  }

  private sendSessionUpdate() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    const defaultSystemPrompt = `You are Blinky, an intelligent offline-first AI desktop tutor and hands-free computer copilot for Windows.
You help users navigate Windows, click UI elements, find controls, explain interface features, and automate computer tasks.
When the user asks you to click, find, open, or interact with something on their screen, invoke the 'control_desktop' tool with the exact command.
Keep your spoken responses natural, concise, friendly, and under 2 sentences whenever possible.`;

    const sessionUpdate = {
      type: 'session.update',
      session: {
        system_prompt: this.config.systemPrompt || defaultSystemPrompt,
        greeting: this.config.greeting || "Hi, I'm Blinky powered by AssemblyAI Universal-3 Pro. How can I guide you on your PC?",
        input: {
          format: {
            encoding: 'audio/pcm16',
            sample_rate: 16000
          }
        },
        output: {
          voice: this.config.voice || 'ivy',
          format: {
            encoding: 'audio/pcm16',
            sample_rate: 24000
          }
        },
        tools: [
          {
            type: 'function',
            name: 'control_desktop',
            description: 'Execute a desktop action or UI automation query on the user\'s PC, such as clicking a button, opening an app, typing, or finding UI elements on screen.',
            parameters: {
              type: 'object',
              properties: {
                action: {
                  type: 'string',
                  description: 'The user query or desktop action (e.g., "click the Chrome icon", "open Notepad", "where is the search bar")'
                }
              },
              required: ['action']
            }
          },
          {
            type: 'function',
            name: 'cancel_desktop_action',
            description: 'Cancel or stop any currently running desktop automation or guide on the PC.',
            parameters: {
              type: 'object',
              properties: {
                reason: {
                  type: 'string',
                  description: 'Reason for stopping'
                }
              }
            }
          }
        ]
      }
    };

    this.ws.send(JSON.stringify(sessionUpdate));
  }

  private async handleMessage(msg: any) {
    const type = msg.type || msg.event;

    switch (type) {
      case 'session.updated':
      case 'session.created':
        console.log('AssemblyAI Voice Agent session initialized successfully');
        break;

      case 'reply.audio':
      case 'response.audio.delta':
      case 'audio.delta': {
        const audioChunk = msg.audio || msg.delta;
        if (audioChunk) {
          this.config.onTurnChange?.('agent');
          this.config.onAgentAudio?.(audioChunk);
        }
        break;
      }

      case 'reply.text':
      case 'response.text.delta': {
        const text = msg.text || msg.delta;
        if (text) {
          this.config.onAgentTranscript?.(text);
        }
        break;
      }

      case 'user.transcript':
      case 'input.transcript': {
        const text = msg.text || msg.transcript;
        const isFinal = !!msg.is_final;
        if (text) {
          this.config.onTurnChange?.('user');
          this.config.onUserTranscript?.(text, isFinal);
        }
        break;
      }

      case 'tool.call': {
        const callId = msg.call_id || msg.id;
        const name = msg.name || msg.function?.name;
        let args = msg.arguments || msg.function?.arguments || {};
        if (typeof args === 'string') {
          try {
            args = JSON.parse(args);
          } catch {}
        }

        if (callId && name && this.config.onToolCall) {
          this.pendingTools.add(callId);
          try {
            const result = await this.config.onToolCall(callId, name, args);
            this.sendToolResult(callId, result || { status: 'completed' });
          } catch (toolErr: any) {
            this.sendToolResult(callId, {
              status: 'error',
              error: toolErr?.message || String(toolErr)
            });
          } finally {
            this.pendingTools.delete(callId);
          }
        }
        break;
      }

      case 'reply.done':
      case 'response.done':
        this.config.onTurnChange?.('idle');
        break;

      case 'interrupted':
      case 'turn.start':
        // User barge-in detected by AssemblyAI turn-taking VAD
        this.config.onTurnChange?.('user');
        break;

      case 'error':
        console.error('AssemblyAI Voice Agent error message:', msg);
        this.config.onError?.(msg.message || msg.error || msg);
        break;

      default:
        // Handle generic transcript or audio payloads
        if (msg.transcript) {
          this.config.onUserTranscript?.(msg.transcript, !!msg.is_final);
        } else if (msg.audio) {
          this.config.onAgentAudio?.(msg.audio);
        }
        break;
    }
  }

  sendAudioChunk(pcmChunk: ArrayBuffer) {
    if (!this.isConnected || !this.ws) return;

    const base64Audio = arrayBufferToBase64(pcmChunk);
    const audioEvent = {
      type: 'input.audio',
      audio: base64Audio
    };

    try {
      this.ws.send(JSON.stringify(audioEvent));
    } catch (err) {
      console.warn('AssemblyAI Voice Agent: Failed to send audio chunk:', err);
    }
  }

  sendToolResult(callId: string, result: any) {
    if (!this.isConnected || !this.ws) return;

    const resultPayload = {
      type: 'tool.result',
      call_id: callId,
      result: typeof result === 'string' ? result : JSON.stringify(result)
    };

    try {
      this.ws.send(JSON.stringify(resultPayload));
    } catch (err) {
      console.warn('AssemblyAI Voice Agent: Failed to send tool result:', err);
    }
  }

  disconnect() {
    if (this.ws) {
      try {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.close();
        }
      } catch {}
      this.ws = null;
    }
    this.isConnectedState = false;
    this.pendingTools.clear();
  }
}

/**
 * Path 2: AssemblyAI Realtime Speech-to-Text API
 * Sub-second streaming transcription over WebSocket powered by Universal-3 Pro.
 * Provides live partial & final transcripts to orchestrate with Blinky's multi-agent tutor.
 */
export class AssemblyAIRealtimeSTT {
  private ws: WebSocket | null = null;
  private isConnectedState = false;
  private onTranscript: (text: string, isFinal: boolean) => void;
  private onError: (err: any) => void;
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
    return this.isConnectedState && this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  connect(preferProxy = true) {
    this.disconnect();

    // Use local Tauri backend proxy (ws://127.0.0.1:9001/assemblyai-stt)
    // which handles the AssemblyAI Authorization header and Universal-3 Pro model parameters.
    const url = preferProxy
      ? 'ws://127.0.0.1:9001/assemblyai-stt'
      : `wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&speech_model=universal-3-5-pro&token=${encodeURIComponent(this.apiKey)}`;

    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      this.onError(e);
      return;
    }

    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this.isConnectedState = true;
      console.log('AssemblyAI Realtime STT: WebSocket opened (Universal-3 Pro).');

      // Flush any queued audio chunks
      while (this.queuedChunks.length > 0) {
        const chunk = this.queuedChunks.shift();
        if (chunk && this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(chunk);
        }
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(typeof event.data === 'string' ? event.data : new TextDecoder().decode(event.data));

        // AssemblyAI v3 WebSocket returns 'Turn' events or transcript objects
        if (data.type === 'Turn') {
          const transcript = (data.transcript || '').trim();
          const isFinal = !!data.end_of_turn;
          if (transcript) {
            this.onTranscript(transcript, isFinal);
          }
        } else if (data.message_type === 'PartialTranscript') {
          const text = (data.text || '').trim();
          if (text) {
            this.onTranscript(text, false);
          }
        } else if (data.message_type === 'FinalTranscript') {
          const text = (data.text || '').trim();
          if (text) {
            this.onTranscript(text, true);
          }
        } else if (data.transcript) {
          this.onTranscript(data.transcript.trim(), !!data.is_final);
        }
      } catch (err) {
        console.warn('AssemblyAI STT parse error:', err);
      }
    };

    this.ws.onerror = (err) => {
      console.error('AssemblyAI Realtime STT error:', err);
      this.onError(err);
    };

    this.ws.onclose = () => {
      this.isConnectedState = false;
      this.ws = null;
    };
  }

  sendAudioChunk(chunk: ArrayBuffer) {
    if (this.isConnected && this.ws) {
      this.ws.send(chunk);
    } else if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
      this.queuedChunks.push(chunk);
    }
  }

  disconnect() {
    if (this.ws) {
      try {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: 'Terminate' }));
          this.ws.close();
        }
      } catch {}
      this.ws = null;
    }
    this.isConnectedState = false;
    this.queuedChunks = [];
  }
}

/**
 * Path 3: AssemblyAI REST Audio Transcription Fallback
 * Direct upload and Universal-3 Pro transcription polling.
 */
export async function transcribeAudioWithAssemblyAI(
  blob: Blob,
  apiKey: string
): Promise<string> {
  if (!apiKey) {
    throw new Error('AssemblyAI API Key is required');
  }

  // 1. Upload audio to AssemblyAI
  const uploadRes = await fetch('https://api.assemblyai.com/v2/upload', {
    method: 'POST',
    headers: {
      Authorization: apiKey,
    },
    body: blob,
  });

  if (!uploadRes.ok) {
    const errorText = await uploadRes.text();
    throw new Error(`AssemblyAI audio upload failed (${uploadRes.status}): ${errorText}`);
  }

  const { upload_url } = await uploadRes.json();
  if (!upload_url) {
    throw new Error('AssemblyAI upload did not return an upload_url');
  }

  // 2. Request transcription with Universal-3 Pro
  const transcriptRes = await fetch('https://api.assemblyai.com/v2/transcript', {
    method: 'POST',
    headers: {
      Authorization: apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      audio_url: upload_url,
      speech_models: ['universal-3-5-pro'],
      punctuate: true,
      format_text: true,
    }),
  });

  if (!transcriptRes.ok) {
    const errorText = await transcriptRes.text();
    throw new Error(`AssemblyAI transcript creation failed: ${errorText}`);
  }

  const { id: transcriptId } = await transcriptRes.json();
  if (!transcriptId) {
    throw new Error('AssemblyAI transcript request did not return an ID');
  }

  // 3. Poll for completion
  const maxAttempts = 60;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, 800));

    const pollRes = await fetch(`https://api.assemblyai.com/v2/transcript/${transcriptId}`, {
      headers: {
        Authorization: apiKey,
      },
    });

    if (!pollRes.ok) continue;

    const data = await pollRes.json();
    if (data.status === 'completed') {
      return (data.text || '').trim();
    } else if (data.status === 'error') {
      throw new Error(`AssemblyAI transcription error: ${data.error || 'Unknown error'}`);
    }
  }

  throw new Error('AssemblyAI transcription timed out');
}
