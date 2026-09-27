import { emit, listen } from '@tauri-apps/api/event';
import { convertFileSrc } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ArrowUp, Bot, Loader2, Minus, Sparkles, X, Settings, Check, Mic, Volume2, Globe, Square, QrCode, Paperclip, Film, Image as ImageIcon, Music, FileVideo } from 'lucide-react';
import { AnchorHTMLAttributes, FormEvent, useEffect, useRef, useState, cloneElement, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import QRCode from 'qrcode';
import { runAutopilotLoop, extractTextToType, shouldPressEnterAfterTyping, isScrollAction, getScrollDirection, isClickInstruction, isSingleActionQuery, createEmptyTutorResult, getPhysicalClickablePoint } from './lib/autopilot';
import {
  getCurrentGuideSteps,
  getDisplaySteps,
  getHighlightSteps,
  mergeGuideHistory,
  shouldCompleteStepOnHighlightClick,
  shouldShowSummaryBubble,
} from './lib/guidance';
import { runTutor, showOverlay, hideOverlay, resizeCommandWindow, getSettings, saveSettings, resizeAndMoveCommandWindow, clickElement, clickScreenPoint, openUrl, typeText, scrollAtPoint, pauseWakeWord, resumeWakeWord, logDebugMessage, confirmRecipeSave, setAgentCursorVisibility, getSecureTransportInfo } from './lib/tauri';

import { linkCitationMarkers, preprocessMarkdown } from './lib/citations';
import { getSarvamErrorMessage } from './lib/tts';
import { SarvamSpeechToTextStream, SarvamTextToSpeechStream } from './lib/sarvamStream';
import {
  AssemblyAIVoiceAgent,
  AssemblyAIRealtimeSTT,
  transcribeAudioWithAssemblyAI,
  floatTo16BitPCM,
  playPCM16Audio
} from './lib/assemblyaiVoice';
import { AdaptiveTransportManager } from './lib/adaptiveTransport';
import type { TutorConversationMessage, TutorProgress, TutorResult } from './lib/types';
import type { SecureTransportInfo } from './lib/tauri';


interface AttachedMedia {
  path: string;
  name: string;
  type: 'video' | 'image' | 'audio' | 'other';
  previewUrl?: string;
}

function getMediaType(filePath: string): 'video' | 'image' | 'audio' | 'other' {
  const ext = filePath.split('.').pop()?.toLowerCase() || '';
  if (['mp4', 'mov', 'mkv', 'avi', 'webm', 'flv', 'wmv', 'm4v'].includes(ext)) return 'video';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'].includes(ext)) return 'image';
  if (['mp3', 'wav', 'aac', 'm4a', 'flac', 'ogg', 'wma'].includes(ext)) return 'audio';
  return 'other';
}

function getFileName(filePath: string): string {
  const parts = filePath.split(/[\\/]/);
  return parts[parts.length - 1] || filePath;
}

interface TargetClickedPayload {
  step?: number;
  target_text?: string;
  instruction?: string;
}

interface TutorRunOptions {
  resetProgress?: boolean;
  preserveStepsDuringRun?: boolean;
}

function getLinkText(children: AnchorHTMLAttributes<HTMLAnchorElement>['children']): string {
  if (typeof children === 'string' || typeof children === 'number') {
    return String(children);
  }

  if (Array.isArray(children)) {
    return children.map(getLinkText).join('');
  }

  return '';
}

function ExternalMarkdownLink({ href, children }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const linkText = getLinkText(children);
  const isCitation = /^\d+$/.test(linkText);

  return (
    <a
      href={href}
      className={isCitation ? 'citation-link' : 'markdown-link'}
      title={isCitation ? `Open source [${linkText}]` : href}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (href) {
          void openUrl(href);
        }
      }}
    >
      {isCitation ? `[${linkText}]` : children}
    </a>
  );
}

/** Renders the desktop command bar and coordinates its interactive workflows. */
export function CommandBar() {
  const [question, setQuestion] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<AttachedMedia[]>([]);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const addAttachedFiles = (paths: string[]) => {
    setAttachedFiles((prev) => {
      const existing = new Set(prev.map((f) => f.path));
      const newItems: AttachedMedia[] = [];
      for (const p of paths) {
        if (!existing.has(p) && p.trim()) {
          const type = getMediaType(p);
          let previewUrl: string | undefined = undefined;
          try {
            if (type === 'image') {
              previewUrl = convertFileSrc(p);
            }
          } catch {
            // ignore
          }
          newItems.push({
            path: p,
            name: getFileName(p),
            type,
            previewUrl,
          });
          existing.add(p);
        }
      }
      return [...prev, ...newItems];
    });
  };

  const removeAttachedFile = (pathToRemove: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.path !== pathToRemove));
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const paths: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const nativePath = (file as any).path || (file as any).webkitRelativePath || file.name;
      if (nativePath) paths.push(nativePath);
    }
    addAttachedFiles(paths);
    e.target.value = '';
  };

  const [isRunning, setIsRunning] = useState(false);
  const isRunningRef = useRef(false);
  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [agentModeEnabled, setAgentModeEnabled] = useState(false);
  const defaultStatus = 'Ask anything on your screen';


  const [isResizing, setIsResizing] = useState(false);
  const resizeRef = useRef<{
    startX: number;
    initialWidth: number;
    initialHeight: number;

    initialX: number;
    initialY: number;
    scaleFactor: number;
    side: 'left' | 'right';
  } | null>(null);

  const startResize = async (event: React.PointerEvent<HTMLDivElement>, side: 'left' | 'right') => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);

    const appWindow = getCurrentWindow();
    const size = await appWindow.innerSize();
    const position = await appWindow.outerPosition();
    const scaleFactor = await appWindow.scaleFactor();

    resizeRef.current = {
      startX: event.screenX,
      initialWidth: size.width / scaleFactor,
      initialHeight: size.height / scaleFactor,
      initialX: position.x / scaleFactor,
      initialY: position.y / scaleFactor,
      scaleFactor,
      side
    };
    setIsResizing(true);
  };

  const handleResize = async (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isResizing || !resizeRef.current) return;

    const { startX, initialWidth, initialHeight, initialX, initialY, scaleFactor, side } = resizeRef.current;
    const dx = (event.screenX - startX) / scaleFactor;

    if (side === 'right') {
      const newWidth = Math.max(560, initialWidth + dx);
      await resizeAndMoveCommandWindow(initialX, initialY, newWidth, initialHeight);
    } else if (side === 'left') {
      const newWidth = Math.max(560, initialWidth - dx);
      const newX = initialX + (initialWidth - newWidth);
      await resizeAndMoveCommandWindow(newX, initialY, newWidth, initialHeight);
    }
  };

  const stopResize = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isResizing) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setIsResizing(false);
    resizeRef.current = null;
  };
  const [status, setStatus] = useState(defaultStatus);
  const statusRef = useRef(defaultStatus);
  useEffect(() => {
    statusRef.current = status;
  }, [status]);
  const [spokenStatus, setSpokenStatus] = useState<string>('');
  const [isTtsActive, setIsTtsActive] = useState<boolean>(false);
  const [steps, setSteps] = useState<any[]>([]);
  const [showGuideCompletionSummary, setShowGuideCompletionSummary] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [shortcut, setShortcut] = useState('Enter');
  const defaultAaiKey = (import.meta as any).env?.VITE_ASSEMBLY_AI_API_KEY || '';
  const [sarvamApiKey, setSarvamApiKey] = useState('');
  const [assemblyaiApiKey, setAssemblyaiApiKey] = useState(defaultAaiKey);
  const assemblyaiApiKeyRef = useRef(defaultAaiKey);
  const [voiceProvider, setVoiceProvider] = useState<'assemblyai' | 'sarvam'>('assemblyai');
  const voiceProviderRef = useRef<'assemblyai' | 'sarvam'>('assemblyai');
  const [assemblyaiVoiceMode, setAssemblyaiVoiceMode] = useState<'agent' | 'realtime_stt'>('agent');
  const assemblyaiAgentRef = useRef<AssemblyAIVoiceAgent | null>(null);
  const assemblyaiSttRef = useRef<AssemblyAIRealtimeSTT | null>(null);
  const assemblyaiAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const [groqApiKey, setGroqApiKey] = useState('');
  const [deepseekApiKey, setDeepseekApiKey] = useState('');
  const [customUrl, setCustomUrl] = useState('');
  const [customModel, setCustomModel] = useState('');
  const [customApiKey, setCustomApiKey] = useState('');
  const [transportInfo, setTransportInfo] = useState<SecureTransportInfo | null>(null);
  const sarvamApiKeyRef = useRef('');

  useEffect(() => {
    sarvamApiKeyRef.current = sarvamApiKey;
  }, [sarvamApiKey]);

  useEffect(() => {
    assemblyaiApiKeyRef.current = assemblyaiApiKey;
  }, [assemblyaiApiKey]);

  useEffect(() => {
    voiceProviderRef.current = voiceProvider;
  }, [voiceProvider]);

  useEffect(() => {
    async function loadInitialSettings() {
      try {
        const s = await getSettings();
        if (s.provider) setProvider(s.provider);
        if (s.shortcut) setShortcut(s.shortcut);
        if (s.voice_provider === 'sarvam' || s.voice_provider === 'assemblyai') {
          setVoiceProvider(s.voice_provider);
          voiceProviderRef.current = s.voice_provider;
        } else {
          const cached = localStorage.getItem('blinky_voice_provider') as 'assemblyai' | 'sarvam' | null;
          if (cached === 'sarvam' || cached === 'assemblyai') {
            setVoiceProvider(cached);
            voiceProviderRef.current = cached;
          }
        }
        if (s.sarvam_api_key) {
          setSarvamApiKey(s.sarvam_api_key);
          sarvamApiKeyRef.current = s.sarvam_api_key;
        }
        if (s.assemblyai_api_key) {
          setAssemblyaiApiKey(s.assemblyai_api_key);
          assemblyaiApiKeyRef.current = s.assemblyai_api_key;
        } else if (defaultAaiKey) {
          setAssemblyaiApiKey(defaultAaiKey);
          assemblyaiApiKeyRef.current = defaultAaiKey;
        }
        if (s.groq_api_key) setGroqApiKey(s.groq_api_key);
        if (s.deepseek_api_key) setDeepseekApiKey(s.deepseek_api_key);
        if (s.custom_url) setCustomUrl(s.custom_url);
        if (s.custom_model) setCustomModel(s.custom_model);
        if (s.custom_api_key) setCustomApiKey(s.custom_api_key);
      } catch (err) {
        console.error('Failed to load initial settings in CommandBar:', err);
      }
    }
    void loadInitialSettings();
  }, []);

  useEffect(() => {
    void getSecureTransportInfo()
      .then(setTransportInfo)
      .catch(() => setTransportInfo(null));
  }, []);

  // Workflow-save prompt (emitted by the agent loop after a successful task)

  const [recipePrompt, setRecipePrompt] = useState<{ recipe_id: string; preview: string[]; intent: string } | null>(null);
  const [recipeBusy, setRecipeBusy] = useState(false);

  // WhatsApp connection states
  const [waBackendUrl, setWaBackendUrl] = useState('http://localhost:3000');
  const [waStatus, setWaStatus] = useState<'loading' | 'disconnected' | 'qr' | 'connected' | 'error'>('loading');
  const [waQr, setWaQr] = useState('');
  const [waError, setWaError] = useState('');
  const [isWaActionLoading, setIsWaActionLoading] = useState(false);
  const [showWaModal, setShowWaModal] = useState(false);
  const waCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const SESSION_ID = 'blinky-default-session';
  const PORTS_TO_SCAN = [3000, 3001, 3002, 3003, 3004, 3005];

  const findWaBackendUrl = async (): Promise<string> => {
    for (const port of PORTS_TO_SCAN) {
      const url = `http://localhost:${port}`;
      try {
        const res = await fetch(`${url}/api/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sessionId: SESSION_ID })
        });
        if (res.ok || res.status === 400) {
          return url;
        }
      } catch (e) {
        // ignore
      }
    }
    return 'http://localhost:3000';
  };

  const connectWhatsApp = async (backendUrl = waBackendUrl) => {
    setIsWaActionLoading(true);
    setWaError('');
    try {
      const res = await fetch(`${backendUrl}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: SESSION_ID })
      });
      if (res.ok) {
        const statusRes = await fetch(`${backendUrl}/api/status`, {
          headers: { 'X-Session-Id': SESSION_ID }
        });
        if (statusRes.ok) {
          const data = await statusRes.json();
          setWaStatus(data.status);
          setWaQr(data.qr || '');
        }
      } else {
        const data = await res.json().catch(() => ({}));
        setWaError(data.error || 'Failed to initialize session');
        setWaStatus('error');
      }
    } catch (err) {
      setWaError('Server communication error');
      setWaStatus('error');
    } finally {
      setIsWaActionLoading(false);
    }
  };

  const logoutWhatsApp = async () => {
    setIsWaActionLoading(true);
    setWaError('');
    try {
      const res = await fetch(`${waBackendUrl}/api/logout`, {
        method: 'POST',
        headers: {
          'X-Session-Id': SESSION_ID,
          'Content-Type': 'application/json'
        }
      });
      if (res.ok) {
        setWaStatus('loading');
        setWaQr('');
      } else {
        const data = await res.json().catch(() => ({}));
        setWaError(data.error || 'Failed to logout');
      }
    } catch (err) {
      setWaError('Server communication error');
    } finally {
      setIsWaActionLoading(false);
    }
  };

  // Discover WhatsApp backend port on mount
  useEffect(() => {
    let active = true;

    async function discover() {
      const url = await findWaBackendUrl();
      if (!active) return;
      setWaBackendUrl(url);
      void connectWhatsApp(url);
    }

    void discover();
    return () => {
      active = false;
    };
  }, []);

  // Keep WhatsApp status fresh so startup state and logout state update without user interaction.
  useEffect(() => {
    let active = true;
    const fetchStatus = async () => {
      try {
        const res = await fetch(`${waBackendUrl}/api/status`, {
          headers: { 'X-Session-Id': SESSION_ID }
        });
        if (!active) return;
        if (res.ok) {
          const data = await res.json();
          setWaStatus(data.status);
          setWaQr(data.qr || '');
          setWaError('');
        } else {
          if (res.status === 404) {
            setWaStatus('disconnected');
          } else {
            const data = await res.json().catch(() => ({}));
            setWaError(data.error || `HTTP error ${res.status}`);
            setWaStatus('error');
          }
        }
      } catch (err) {
        if (!active) return;
        setWaStatus('disconnected');
      }
    };

    void fetchStatus();
    const interval = setInterval(fetchStatus, 3000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [showSettings, showWaModal, waBackendUrl]);

  // Draw QR code to canvas
  useEffect(() => {
    if (waStatus === 'qr' && waQr && waCanvasRef.current) {
      QRCode.toCanvas(
        waCanvasRef.current,
        waQr,
        {
          width: 180,
          margin: 2,
          color: {
            dark: '#140f13',
            light: '#ffffff'
          }
        },
        (error) => {
          if (error) console.error('Failed to render QR Code:', error);
        }
      );
    }
  }, [waStatus, waQr]);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const isRecordingRef = useRef(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const lastQueryRef = useRef<string>('');
  const completedTargetsRef = useRef<string[]>([]);
  const completedInstructionsRef = useRef<string[]>([]);
  const failedTargetsRef = useRef<string[]>([]);
  const failedRefsRef = useRef<string[]>([]);
  const currentGuideStepsRef = useRef<any[]>([]);
  const workflowStartedWithReadbackRef = useRef(false);
  const conversationHistoryRef = useRef<TutorConversationMessage[]>([]);
  const runIdRef = useRef(0);
  const cancelledRunIdsRef = useRef<Set<number>>(new Set());
  const latestTranscriptRef = useRef<string>('');
  const isStartingRecordingRef = useRef(false);

  // WebTransport and WebSocket streaming refs
  const sttStreamRef = useRef<SarvamSpeechToTextStream | null>(null);
  const ttsStreamRef = useRef<SarvamTextToSpeechStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const transportManagerRef = useRef<AdaptiveTransportManager | null>(null);
  const transportStateRef = useRef<'WEBTRANSPORT' | 'WEBSOCKET'>('WEBTRANSPORT');
  const ttsAnalyserRef = useRef<AnalyserNode | null>(null);

  // TTS Streaming state
  const speechBufferRef = useRef<string>('');
  const ttsTextQueueRef = useRef<{ text: string, isHidden?: boolean, startWordIdx?: number, wordsCount?: number }[]>([]);
  const ttsAudioQueueRef = useRef<string[]>([]);
  const isFetchingTtsRef = useRef<boolean>(false);
  const isPlayingTtsRef = useRef<boolean>(false);
  const hasStreamedTtsRef = useRef<boolean>(false);

  const [activeWordIndex, setActiveWordIndex] = useState<number>(-1);
  const wordTimersRef = useRef<number[]>([]);
  const spokenWordsAccumulatorRef = useRef<number>(0);

  const pushToTtsQueue = (text: string, isHidden?: boolean) => {
    const cleanSentence = text.trim();
    if (!cleanSentence) return;

    const wordsCount = cleanSentence.split(/\s+/).filter(Boolean).length;
    const startWordIdx = spokenWordsAccumulatorRef.current;
    spokenWordsAccumulatorRef.current += wordsCount;

    ttsTextQueueRef.current.push({
      text: cleanSentence,
      isHidden,
      startWordIdx,
      wordsCount
    });
  };

  const rememberCompletedStep = (targetText?: string, instruction?: string, plannedTarget?: string) => {
    const cleanTarget = targetText?.trim();
    const cleanInstruction = instruction?.trim();
    const cleanPlanned = plannedTarget?.trim();

    if (cleanTarget && !completedTargetsRef.current.includes(cleanTarget)) {
      completedTargetsRef.current = [...completedTargetsRef.current, cleanTarget];
    }
    if (cleanPlanned && !completedTargetsRef.current.includes(cleanPlanned)) {
      completedTargetsRef.current = [...completedTargetsRef.current, cleanPlanned];
    }

    if (cleanInstruction && !completedInstructionsRef.current.includes(cleanInstruction)) {
      completedInstructionsRef.current = [...completedInstructionsRef.current, cleanInstruction];
    }
  };

  const rememberFailedStep = (targetText?: string, ref?: string) => {
    const cleanTarget = targetText?.trim();
    const cleanRef = ref?.trim();

    if (cleanTarget && !failedTargetsRef.current.includes(cleanTarget)) {
      failedTargetsRef.current = [...failedTargetsRef.current, cleanTarget];
    }

    if (cleanRef && !failedRefsRef.current.includes(cleanRef)) {
      failedRefsRef.current = [...failedRefsRef.current, cleanRef];
    }
  };

  const stopSpeaking = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    if (assemblyaiAudioSourceRef.current) {
      try {
        assemblyaiAudioSourceRef.current.stop();
      } catch {}
      assemblyaiAudioSourceRef.current = null;
    }
    activeSourcesRef.current.forEach((source) => {
      try {
        source.stop();
      } catch {}
    });
    activeSourcesRef.current = [];
    if (ttsStreamRef.current) {
      ttsStreamRef.current.disconnect();
      ttsStreamRef.current = null;
    }

    // Clear word highlight timers
    wordTimersRef.current.forEach((timerId) => clearTimeout(timerId));
    wordTimersRef.current = [];
    setActiveWordIndex(-1);
    spokenWordsAccumulatorRef.current = 0;

    ttsTextQueueRef.current = [];
    ttsAudioQueueRef.current = [];
    isFetchingTtsRef.current = false;
    isPlayingTtsRef.current = false;
    speechBufferRef.current = '';
    nextPlayTimeRef.current = 0;

    setIsSpeaking(false);
    setIsTtsActive(false);
  };

  // Initialize Adaptive Transport Manager when API key is loaded
  useEffect(() => {
    if (sarvamApiKey) {
      const wtUrl = import.meta.env.VITE_SARVAM_GATEWAY_WT_URL || 'wt://gateway.blinky.internal/sarvam-stream';
      const wsUrl = `wss://api.sarvam.ai/speech-to-text-stream?api-subscription-key=${encodeURIComponent(sarvamApiKey)}`;
      
      transportManagerRef.current = new AdaptiveTransportManager(
        wtUrl,
        wsUrl,
        sarvamApiKey,
        (state) => {
          transportStateRef.current = state;
          console.log(`Adaptive network engine transitioned to: ${state}`);
        }
      );
      void transportManagerRef.current.reEvaluateConnection();
    }
  }, [sarvamApiKey]);

  // Cleanup audio and streams on unmount
  useEffect(() => {
    return () => {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
      }
      activeSourcesRef.current.forEach((source) => {
        try {
          source.stop();
        } catch {}
      });
      if (ttsStreamRef.current) {
        ttsStreamRef.current.disconnect();
      }
      if (sttStreamRef.current) {
        sttStreamRef.current.disconnect();
      }
    };
  }, []);

  // Use a ref to avoid stale closure for the fetch queue function
  const processTtsFetchQueueRef = useRef<() => void>(() => {});

  // Listen for real-time status and streaming chunks from python worker
  useEffect(() => {
    let unlistenStatus: Promise<any>;
    let unlistenChunk: Promise<any>;

    unlistenStatus = listen<{ phase: string; message: string }>('blinky://tutor-status', (event) => {
      setStatus(event.payload.message);
    });

    // Workflow-save prompt from the agent loop
    const unlistenRecipe = listen<{ recipe_id: string; preview: string[]; intent: string }>(
      'blinky://recipe-prompt',
      (event) => {
        setRecipePrompt(event.payload);
      }
    );

    unlistenChunk = listen<{ message: string }>('blinky://tutor-chunk', (event) => {
      const msg = event.payload.message;
      setStatus((prev) => {
        if (
          prev === 'Thinking...' ||
          prev === 'Reading the screen...' ||
          prev === 'Synthesizing streamed answer...' ||
          prev === 'Answering directly from your pre-trained knowledge base...' ||
          prev.startsWith('Searching SearXNG') ||
          prev.startsWith('Fetching content') ||
          prev.startsWith('Cleaning and filtering')
        ) {
          return msg;
        }
        return prev + msg;
      });
    });

    return () => {
      void unlistenStatus.then((dispose) => dispose());
      void unlistenChunk.then((dispose) => dispose());
      void unlistenRecipe.then((dispose) => dispose());
    };
  }, []);

  // Callbacks refs to avoid stale closures in WebSockets
  const onTranscriptRef = useRef<(transcript: string, isFinal: boolean) => void>(() => {});
  const onAudioChunkRef = useRef<(base64Audio: string) => void>(() => {});

  // Update refs on every render
  onTranscriptRef.current = (transcript, isFinal) => {
    const cleanText = (transcript || '').trim();
    if (cleanText) {
      setQuestion(cleanText);
      latestTranscriptRef.current = cleanText;
      if (isFinal) {
        setStatus(`Searching for: "${cleanText}"`);
        stopRecording();
        void executeTutor(cleanText, true);
      }
    }
  };

  onAudioChunkRef.current = async (base64Audio) => {
    if (!audioCtxRef.current) return;
    const binary = atob(base64Audio);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    
    try {
      let audioBuffer: AudioBuffer;
      try {
        audioBuffer = await audioCtxRef.current.decodeAudioData(bytes.buffer.slice(0));
      } catch (decodeErr) {
        const isMp3 = bytes.length >= 3 && (
          (bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33) ||
          (bytes[0] === 0xFF && (bytes[1] & 0xE0) === 0xE0)
        );
        if (isMp3) {
          throw new Error('Failed to decode MP3 data: ' + (decodeErr instanceof Error ? decodeErr.message : String(decodeErr)));
        }
        const validByteLength = bytes.buffer.byteLength - (bytes.buffer.byteLength % 2);
        const int16Array = new Int16Array(bytes.buffer, 0, validByteLength / 2);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
          float32Array[i] = int16Array[i] / 32768.0;
        }
        audioBuffer = audioCtxRef.current.createBuffer(1, float32Array.length, 16000);
        audioBuffer.getChannelData(0).set(float32Array);
      }

      const source = audioCtxRef.current.createBufferSource();
      source.buffer = audioBuffer;
      if (!ttsAnalyserRef.current) {
        ttsAnalyserRef.current = audioCtxRef.current.createAnalyser();
        ttsAnalyserRef.current.connect(audioCtxRef.current.destination);
      }
      source.connect(ttsAnalyserRef.current);

      const startTime = Math.max(audioCtxRef.current.currentTime, nextPlayTimeRef.current);
      source.start(startTime);
      nextPlayTimeRef.current = startTime + audioBuffer.duration;
      activeSourcesRef.current.push(source);

      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
        if (activeSourcesRef.current.length === 0) {
          setIsSpeaking(false);
        }
      };
    } catch (e) {
      console.error('Failed to decode incoming voice buffer:', e);
    }
  };

  const processTtsFetchQueue = async () => {
  };

  // Update ref so useEffect closure always uses the latest state
  processTtsFetchQueueRef.current = processTtsFetchQueue;

  const processTtsPlayQueue = async () => {
  };

  const speakText = async (summaryText: string, stepsList: any[], options: { includeSteps?: boolean } = {}) => {
  };

  const speakResponse = () => {
  };

  useEffect(() => {
    let rafId: number;
    const loop = () => {
      if (isSpeaking && ttsAnalyserRef.current && glowContainerRef.current) {
        const dataArray = new Uint8Array(ttsAnalyserRef.current.frequencyBinCount);
        ttsAnalyserRef.current.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const val = (dataArray[i] - 128) / 128;
          sum += val * val;
        }
        const rms = Math.sqrt(sum / dataArray.length);
        const normalizedVolume = Math.min(1, rms * 8); // Multiplier tunes glow sensitivity to TTS

        void emit('blinky://vad-update', { volume: normalizedVolume });
        
        rafId = requestAnimationFrame(loop);
      } else if (!isSpeaking && !isRecording) {
        void emit('blinky://vad-update', { volume: 0 });
      }
    };

    if (isSpeaking) {
      rafId = requestAnimationFrame(loop);
    }
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [isSpeaking, isRecording]);

  const handleAudioTranscription = async (blob: Blob) => {
    const currentVP = voiceProviderRef.current;
    if (currentVP === 'assemblyai') {
      let aaiKey = assemblyaiApiKey || assemblyaiApiKeyRef.current;
      if (!aaiKey) {
        aaiKey = (import.meta as any).env?.VITE_ASSEMBLY_AI_API_KEY || '';
      }
      if (!aaiKey) {
        try {
          const s = await getSettings();
          if (s.assemblyai_api_key) {
            aaiKey = s.assemblyai_api_key;
            setAssemblyaiApiKey(s.assemblyai_api_key);
            assemblyaiApiKeyRef.current = s.assemblyai_api_key;
          }
        } catch {}
      }

      if (!aaiKey) {
        setStatus('Please set your AssemblyAI API Key in settings first.');
        void resumeWakeWord();
        return;
      }

      setStatus('Transcribing with AssemblyAI Universal-3 Pro...');
      try {
        const transcript = await transcribeAudioWithAssemblyAI(blob, aaiKey);
        if (transcript) {
          setStatus(`Searching for: "${transcript}"`);
          void executeTutor(transcript, true);
          return;
        } else {
          setStatus('Could not hear anything clearly.');
          void resumeWakeWord();
          return;
        }
      } catch (err: any) {
        console.error('AssemblyAI transcription error:', err);
        setStatus(`AssemblyAI STT error: ${err?.message || err}`);
        void resumeWakeWord();
        return;
      }
    }

    const key = sarvamApiKey || sarvamApiKeyRef.current;
    if (!key) {
      setStatus('Please set your Sarvam AI API Key in settings first.');
      void resumeWakeWord();
      return;
    }
    
    setStatus('Transcribing with Sarvam AI...');
    try {
      const formData = new FormData();
      formData.append('file', blob, 'query.webm');
      formData.append('model', 'saaras:v3');
      formData.append('language_code', 'en-IN');

      const res = await fetch('https://api.sarvam.ai/speech-to-text', {
        method: 'POST',
        headers: {
          'api-subscription-key': key,
        },
        body: formData,
      });

      if (!res.ok) {
        let payload: any = {};
        try { payload = await res.json(); } catch {}
        throw new Error(getSarvamErrorMessage(payload, res.status));
      }

      const data = await res.json();
      const transcript = data.transcript?.trim() || '';

      if (transcript) {
        setStatus(`Searching for: "${transcript}"`);
        void executeTutor(transcript, true);
      } else {
        setStatus('Could not hear anything clearly.');
        void resumeWakeWord();
      }
    } catch (err: any) {
      console.error('STT error:', err);
      setStatus(`Transcription failed: ${err.message}`);
      void resumeWakeWord();
    }
  };

  const startRecording = async () => {
    if (isStartingRecordingRef.current) return;
    isStartingRecordingRef.current = true;

    const currentVP = voiceProviderRef.current;
    let aaiKey = assemblyaiApiKey || assemblyaiApiKeyRef.current;
    let key = sarvamApiKey || sarvamApiKeyRef.current;

    if (currentVP === 'assemblyai') {
      if (!aaiKey) {
        aaiKey = (import.meta as any).env?.VITE_ASSEMBLY_AI_API_KEY || '';
      }
      if (!aaiKey) {
        try {
          const s = await getSettings();
          if (s.assemblyai_api_key) {
            setAssemblyaiApiKey(s.assemblyai_api_key);
            assemblyaiApiKeyRef.current = s.assemblyai_api_key;
            aaiKey = s.assemblyai_api_key;
          }
        } catch {}
      }
      if (!aaiKey) {
        setStatus('Please set your AssemblyAI API Key in settings first.');
        isStartingRecordingRef.current = false;
        return;
      }
    } else {
      if (!key) {
        try {
          const s = await getSettings();
          if (s.sarvam_api_key) {
            setSarvamApiKey(s.sarvam_api_key);
            sarvamApiKeyRef.current = s.sarvam_api_key;
            key = s.sarvam_api_key;
          }
        } catch {}
      }
      if (!key) {
        setStatus('Please set your Sarvam AI API Key in settings first.');
        isStartingRecordingRef.current = false;
        return;
      }
    }

    await pauseWakeWord();
    await new Promise(resolve => setTimeout(resolve, 300));
    void showOverlay();

    // Ensure AudioContext is initialized before starting recording (e.g. on hotkey first start)
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      } else if (audioCtxRef.current.state === 'suspended') {
        await audioCtxRef.current.resume();
      }
    } catch (ctxErr) {
      console.warn('AudioContext initialization note:', ctxErr);
    }

    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      (mediaRecorderRef as any).current = mediaRecorder;
      
      const audioChunks: BlobPart[] = [];
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };
      
      // Setup VAD using AudioContext
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
      }
      if (audioCtxRef.current.state === 'suspended') {
        await audioCtxRef.current.resume();
      }
      const audioCtx = audioCtxRef.current;
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);

      // Initialize AssemblyAI Voice Connection if key is present and provider is assemblyai
      if (currentVP === 'assemblyai' && aaiKey && assemblyaiVoiceMode === 'agent') {
        const agent = new AssemblyAIVoiceAgent({
          apiKey: aaiKey,
          onAgentAudio: (base64Audio) => {
            if (assemblyaiAudioSourceRef.current) {
              try { assemblyaiAudioSourceRef.current.stop(); } catch {}
            }
            setIsSpeaking(true);
            if (audioCtxRef.current) {
              const src = playPCM16Audio(audioCtxRef.current, base64Audio, 24000, ttsAnalyserRef.current || undefined);
              assemblyaiAudioSourceRef.current = src;
              src.onended = () => {
                setIsSpeaking(false);
              };
            }
          },
          onAgentTranscript: (text) => {
            setStatus(text);
            setSpokenStatus(text);
          },
          onUserTranscript: (text, isFinal) => {
            setQuestion(text);
            if (isFinal) {
              setStatus(`Heard: "${text}"`);
            }
          },
          onToolCall: async (callId, name, args) => {
            console.log(`AssemblyAI Voice Agent invoked tool: ${name}`, args);
            if (name === 'control_desktop') {
              const action = args.action || '';
              setStatus(`Blinky executing: "${action}"`);
              try {
                await executeTutor(action, false);
                return { status: 'success', message: `Completed desktop action: ${action}` };
              } catch (e: any) {
                return { status: 'error', message: e?.message || String(e) };
              }
            } else if (name === 'cancel_desktop_action') {
              stopCurrentRun();
              return { status: 'success', message: 'Cancelled desktop action.' };
            }
            return { status: 'unknown_tool' };
          },
          onTurnChange: (turn) => {
            if (turn === 'user') {
              if (assemblyaiAudioSourceRef.current) {
                try { assemblyaiAudioSourceRef.current.stop(); } catch {}
                assemblyaiAudioSourceRef.current = null;
              }
              setIsSpeaking(false);
            }
          },
          onError: (err) => {
            console.error('AssemblyAI Voice Agent error:', err);
          }
        });
        agent.connect();
        assemblyaiAgentRef.current = agent;
      } else if (currentVP === 'assemblyai' && aaiKey && assemblyaiVoiceMode === 'realtime_stt') {
        const stt = new AssemblyAIRealtimeSTT(
          aaiKey,
          (transcript, isFinal) => {
            setQuestion(transcript);
            if (isFinal) {
              setStatus(`Searching for: "${transcript}"`);
              void executeTutor(transcript, true);
              stopRecording();
            }
          },
          (err) => {
            console.error('AssemblyAI Realtime STT error:', err);
          }
        );
        stt.connect();
        assemblyaiSttRef.current = stt;
      }
      
      let hasSpoken = false;
      let silenceStartTime = 0;
      let silenceTimeoutTriggered = false;
      const SILENCE_THRESHOLD = 0.015;
      const SPEECH_THRESHOLD = 0.035;
      const SILENCE_DURATION_MS = 800;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);

        // Stream PCM16 chunk to active AssemblyAI connection
        const pcmChunk = floatTo16BitPCM(inputData);
        if (assemblyaiAgentRef.current?.isConnected) {
          assemblyaiAgentRef.current.sendAudioChunk(pcmChunk);
        } else if (assemblyaiSttRef.current?.isConnected) {
          assemblyaiSttRef.current.sendAudioChunk(pcmChunk);
        }

        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);

        const normalizedVolume = Math.min(1, rms * 15);
        void emit('blinky://vad-update', { volume: normalizedVolume });

        if (rms > SPEECH_THRESHOLD) {
          if (!hasSpoken) {
            hasSpoken = true;
          }
          silenceStartTime = 0;
        } else if (hasSpoken && rms < SILENCE_THRESHOLD) {
          const now = Date.now();
          if (silenceStartTime === 0) {
            silenceStartTime = now;
          } else if (now - silenceStartTime > SILENCE_DURATION_MS) {
            if (!silenceTimeoutTriggered) {
              silenceTimeoutTriggered = true;
              console.log("VAD: Local silence timeout reached. Stopping recording and submitting query.");
              
              if ((mediaRecorderRef as any).current?.state === 'recording') {
                stopRecording();
              }
            }
          }
        }
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      mediaRecorder.onstop = () => {
        if (stream) {
          stream.getTracks().forEach((track) => track.stop());
        }
        try { processor.disconnect(); source.disconnect(); } catch {}
        // If real-time stream did not execute, run audio transcription
        if (!assemblyaiAgentRef.current?.isConnected && !assemblyaiSttRef.current?.isConnected) {
          const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
          void handleAudioTranscription(audioBlob);
        }
      };
      
      mediaRecorder.start();
      setIsRecording(true);
      setStatus(
        currentVP === 'assemblyai'
          ? assemblyaiVoiceMode === 'agent'
            ? '⚡ AssemblyAI Voice Agent Listening (Universal-3 Pro)...'
            : '🎙️ AssemblyAI Realtime STT Listening...'
          : '🎙️ Sarvam AI Listening... Click mic to stop.'
      );
      
      // Auto-stop after 12 seconds as a fallback
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          stopRecording();
        }
      }, 12000);
      
    } catch (err) {
      console.error('Error starting audio recording:', err);
      setStatus('Microphone access failed or was denied.');
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      void resumeWakeWord();
    } finally {
      isStartingRecordingRef.current = false;
    }
  };

  const stopRecording = () => {
    if (assemblyaiAgentRef.current) {
      assemblyaiAgentRef.current.disconnect();
      assemblyaiAgentRef.current = null;
    }
    if (assemblyaiSttRef.current) {
      assemblyaiSttRef.current.disconnect();
      assemblyaiSttRef.current = null;
    }
    if (mediaRecorderRef.current) {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
      mediaRecorderRef.current = null;
      setIsRecording(false);

      void emit('blinky://vad-update', { volume: 0 });
    }
  };

  const toggleRecording = () => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
    } else if (audioCtxRef.current.state === 'suspended') {
      void audioCtxRef.current.resume();
    }

    if (isRecording) {
      stopRecording();
    } else {
      stopSpeaking();
      void startRecording();
    }
  };

  function currentProgress(): TutorProgress {
    return {
      completed_targets: completedTargetsRef.current,
      completed_instructions: completedInstructionsRef.current,
      failed_targets: failedTargetsRef.current,
      failed_refs: failedRefsRef.current,
    };
  }

  async function executeTutor(
    queryText: string,
    shouldSpeakAfter: boolean,
    options: TutorRunOptions = {},
  ) {
    if (isRunningRef.current) return;
    isRunningRef.current = true;
    let effectiveQuery = queryText.trim().replace(/^(hey\s+)?blinky[\s,.:;!?]*/i, '').trim();
    if (attachedFiles.length > 0) {
      const pathsStr = attachedFiles.map((f) => f.path).join(', ');
      const prefix = `[Referenced Files: ${pathsStr}]`;
      if (!effectiveQuery.includes('[Referenced Files:')) {
        effectiveQuery = effectiveQuery ? `${prefix} ${effectiveQuery}` : `${prefix} merge these videos`;
      }
      setAttachedFiles([]);
    }
    if (!effectiveQuery) return;

    const runId = runIdRef.current + 1;
    runIdRef.current = runId;

    // Immediately enable streaming TTS if requested
    workflowStartedWithReadbackRef.current = shouldSpeakAfter;
    hasStreamedTtsRef.current = false;
    setIsTtsActive(shouldSpeakAfter);
    setSpokenStatus('Thinking...');

    if (options.resetProgress) {
      completedTargetsRef.current = [];
      completedInstructionsRef.current = [];
      failedTargetsRef.current = [];
      failedRefsRef.current = [];
      currentGuideStepsRef.current = [];
      setSteps([]);
      setShowGuideCompletionSummary(false);
      lastQueryRef.current = '';
      conversationHistoryRef.current = [];
    }

    const previousQuestion = lastQueryRef.current || undefined;
    const conversationHistory = conversationHistoryRef.current.slice(-8);

    setIsRunning(true);
    setStatus('Thinking...');
    if (!options.preserveStepsDuringRun) {
      setSteps([]);
    }
    stopSpeaking();
    void pauseWakeWord();
    
    const currentWindow = getCurrentWindow();
    let isPointing = false;
    try {
      let result: TutorResult;
      if (agentModeEnabled) {
        // Run the agent first — it may handle everything via MCP tools
        const agentResult = await runTutor(effectiveQuery, previousQuestion, currentProgress(), conversationHistory, false, true);

        // If agent handled it purely via backend tool without UI steps, use its result directly.
        // Otherwise, run the autopilot loop so the AI cursor moves, glides, and clicks on screen.
        if (agentResult.computer_use && (!agentResult.steps || agentResult.steps.length === 0)) {
          result = agentResult;
        } else {
          // Show overlay window so AI cursor is visible on screen
          await showOverlay();

          // Vision-guided autopilot loop (screen-based clicking)
          const isSingleAction = isSingleActionQuery(effectiveQuery);
          let firstObservation: TutorResult | null = null;
          const autopilot = await runAutopilotLoop({
            maxAttempts: isSingleAction ? 1 : 5,
            maxRetriesPerStep: 2,
            observeAfterAction: !isSingleAction,
            isCancelled: () => cancelledRunIdsRef.current.has(runId),
            onStepFailed: (failedStep, retryCount) => {
              setStatus(`Action had no effect. Rethinking next step (Attempt ${retryCount})...`);
              rememberFailedStep(failedStep.target_text, failedStep.target_ref || failedStep.match?.ref);
            },
            observe: async () => {
              if (cancelledRunIdsRef.current.has(runId)) {
                return createEmptyTutorResult();
              }
              if (!firstObservation) {
                firstObservation = agentResult;
                return firstObservation;
              }
              return runTutor(effectiveQuery, previousQuestion, currentProgress(), conversationHistory, false, true);
            },
            act: async (point, step) => {
              if (cancelledRunIdsRef.current.has(runId)) return;
              const plannedTarget = (step as any).planned_target;
              // Prefer the element rung. cua-driver resolves the labelled control
              // inside the window that owns the point and invokes it through UIA:
              // it stays in the background, keeps the real pointer still, and does
              // not depend on the target being the topmost window. The point-only
              // click is the fallback for surfaces with no element tree (canvas,
              // video, WebGL) and for a step that carries no target text.
              const label = String((step as any).target_text || plannedTarget || '').trim();
              const click = async () => {
                if (label) {
                  await clickElement(point.x, point.y, label);
                } else {
                  await clickScreenPoint(point.x, point.y);
                }
              };
              if (isScrollAction(step.instruction)) {
                const direction = getScrollDirection(step.instruction);
                setStatus(`Autopilot scrolling ${direction}...`);
                rememberCompletedStep(step.target_text, step.instruction, plannedTarget);
                await scrollAtPoint(point.x, point.y, direction, 3);
              } else {
                const textToType = (step as any).text_to_type || extractTextToType(step.instruction);
                if (textToType) {
                  setStatus(`Autopilot typing "${textToType}"...`);
                  rememberCompletedStep(step.target_text, step.instruction, plannedTarget);
                  await click();
                  await new Promise((resolve) => setTimeout(resolve, 150));
                  if (cancelledRunIdsRef.current.has(runId)) return;
                  const pressEnter = (step as any).key?.toLowerCase() === 'enter' || shouldPressEnterAfterTyping(step.instruction);
                  await typeText(point.x, point.y, textToType, pressEnter);
                } else {
                  setStatus(`Autopilot clicking (${point.x}, ${point.y})...`);
                  rememberCompletedStep(step.target_text, step.instruction, plannedTarget);
                  await click();
                }
              }
            },
          });
          if ((autopilot.stopReason === 'complete' || autopilot.stopReason === 'single_action') && autopilot.attempts > 0) {
            const firstStep = agentResult.steps?.find((candidate) => candidate.instruction.trim());
            result = {
              ...autopilot.finalResult,
              summary: isSingleAction
                ? `Clicked ${firstStep?.target_text || 'the target'}.`
                : `Autopilot successfully completed the task!`,
              steps: [],
            };
          } else if (autopilot.stopReason === 'unsafe_step') {

            const nextStep = autopilot.finalResult.steps.find((candidate) => candidate.instruction.trim());
            const blockedLabel = nextStep?.target_text || nextStep?.instruction || 'the next action';
            result = {
              ...autopilot.finalResult,
              summary: `Autopilot paused because "${blockedLabel}" requires manual interaction for safety.`,
            };
          } else if (autopilot.stopReason === 'missing_target') {
            result = {
              ...autopilot.finalResult,
              summary: `Autopilot stopped because it could not locate the next target on the screen. Please guide me manually.`,
            };
          } else if (autopilot.stopReason === 'unchanged_after_action') {
            result = {
              ...autopilot.finalResult,
              summary: `Autopilot stopped because the screen did not change after the last action. Please try manually.`,
            };
          } else if (autopilot.stopReason === 'max_attempts') {
            result = {
              ...autopilot.finalResult,
              summary: `Autopilot reached the maximum number of attempts. Please complete the remaining steps manually.`,
            };
          } else {
            result = autopilot.finalResult;
          }
        }
      } else {
        result = await runTutor(effectiveQuery, previousQuestion, currentProgress(), conversationHistory, webSearchEnabled);

        await logDebugMessage(`[executeTutor] (Standard) Received result from backend. Steps count: ${result.steps?.length || 0}`);
        if (result.steps && result.steps.length > 0) {
          const step = result.steps[0];
          await logDebugMessage(`[executeTutor] (Standard) Step 1: instruction="${step.instruction}", target_ref="${step.target_ref}", target_text="${step.target_text}", hasMatch=${!!step.match}`);
        }

        // Auto-trigger autopilot click for locator fast path results with click instructions
        const clickStep = result.steps?.find((s) => s.instruction && s.match);
        if (clickStep) {
          const isClick = isClickInstruction(clickStep.instruction);
          await logDebugMessage(`[executeTutor] (Standard) Click step candidate: instruction="${clickStep.instruction}", isClickInstruction=${isClick}`);
        }

        if (clickStep && isClickInstruction(clickStep.instruction)) {
          await logDebugMessage(`[executeTutor] (Standard) Triggering autopilot click at physical match x=${clickStep.match?.x}, y=${clickStep.match?.y}`);
          const autopilot = await runAutopilotLoop({
            maxAttempts: 1,
            observeAfterAction: false,
            isCancelled: () => cancelledRunIdsRef.current.has(runId),
            observe: async () => result,
            act: async (point, step) => {
              if (cancelledRunIdsRef.current.has(runId)) return;
              await logDebugMessage(`[executeTutor] (Standard) Autopilot act: clicking point x=${point.x}, y=${point.y}`);
              setStatus(`Clicking (${point.x}, ${point.y})...`);
              const label = String(step.target_text || '').trim();
              if (label) {
                await clickElement(point.x, point.y, label);
              } else {
                await clickScreenPoint(point.x, point.y);
              }
            },
          });
          if (autopilot.stopReason === 'complete' || autopilot.attempts > 0) {
            await logDebugMessage(`[executeTutor] (Standard) Autopilot completed with stopReason=${autopilot.stopReason}`);
            result = {
              ...result,
              summary: `Clicked ${clickStep.target_text || 'the target'}.`,
              steps: [],
            };
          }
        }
      }
      if (cancelledRunIdsRef.current.has(runId)) {
        return;
      }
      const isContinuation = !!result.is_continuation;

      if (!isContinuation) {
        if (!agentModeEnabled) {
          completedTargetsRef.current = [];
          completedInstructionsRef.current = [];
        }
        currentGuideStepsRef.current = [];
        setSteps([]);
        setShowGuideCompletionSummary(false);
        lastQueryRef.current = effectiveQuery;
      }

      const displaySteps = getDisplaySteps(result.steps || []);
      const currentGuideSteps = getCurrentGuideSteps(displaySteps, currentProgress());
      currentGuideStepsRef.current = currentGuideSteps;
      const hasCompletedProgress =
        completedTargetsRef.current.length > 0 || completedInstructionsRef.current.length > 0;
      const highlightSteps = getHighlightSteps(currentGuideSteps);
      await emit('blinky://guidance', { ...result, steps: currentGuideSteps });
      isPointing = false;
      if (highlightSteps.length > 0) {
        await showOverlay();
        const primaryHighlight = highlightSteps[0];
        if (primaryHighlight && primaryHighlight.match) {
          isPointing = true;
          const point = getPhysicalClickablePoint(primaryHighlight, result);
          void emit('blinky://agent-cursor-move', {
            x: point.x,
            y: point.y,
            instruction: primaryHighlight.instruction,
          });
        }
      } else {
        await hideOverlay();
      }
      await currentWindow.setFocus();
      setStatus(result.summary);
      const newHistoryEntries: TutorConversationMessage[] = [
        { role: 'student', content: effectiveQuery },
        { role: 'blinky', content: result.summary },
      ];
      conversationHistoryRef.current = [
        ...conversationHistoryRef.current,
        ...newHistoryEntries,
      ].slice(-10);
      setShowGuideCompletionSummary(
        (hasCompletedProgress && currentGuideSteps.length === 0 && Boolean(result.summary))
        || Boolean(result.computer_use)
      );
      setSteps((previousSteps) => mergeGuideHistory(previousSteps, currentGuideSteps, currentProgress()));
      setQuestion('');
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
      }
    } catch (error) {
      if (cancelledRunIdsRef.current.has(runId)) {
        return;
      }
      await currentWindow.setFocus();
      setStatus(error instanceof Error ? error.message : String(error));
      setSteps([]);
    } finally {
      cancelledRunIdsRef.current.delete(runId);
      if (runIdRef.current === runId) {
        isRunningRef.current = false;
        setIsRunning(false);
        if (!isPointing) {
          void emit('blinky://agent-cursor-done', {});
        }
        if (!shouldSpeakAfter && !isRecording && !isSpeaking) {
          void resumeWakeWord();
        }
      }
    }
  }

  function stopCurrentRun() {
    const runId = runIdRef.current;
    if (!isRunningRef.current || runId === 0) return;
    cancelledRunIdsRef.current.add(runId);
    isRunningRef.current = false;
    setIsRunning(false);
    setStatus('Stopped.');
    setSteps([]);
    void hideOverlay();
    void emit('blinky://agent-cursor-done', {});
    stopSpeaking();
    if (!isRecording) {
      void resumeWakeWord();
    }
  }

  // Load settings on mount
  useEffect(() => {
    getSettings()
      .then((settings) => {
        setProvider(settings.provider);
        setShortcut(settings.shortcut);
        setSarvamApiKey(settings.sarvam_api_key || '');
        setGroqApiKey(settings.groq_api_key || '');
        setDeepseekApiKey(settings.deepseek_api_key || '');
        setCustomUrl(settings.custom_url || '');
        setCustomModel(settings.custom_model || '');
        setCustomApiKey(settings.custom_api_key || '');
      })
      .catch((err) => console.error('Failed to load settings:', err));
  }, []);

  // Always focus the window on mouse enter to ensure one-click interaction
  useEffect(() => {
    const handleMouseEnter = () => {
      void getCurrentWindow().setFocus();
    };

    document.addEventListener('mouseenter', handleMouseEnter);
    return () => {
      document.removeEventListener('mouseenter', handleMouseEnter);
    };
  }, []);

  // Global shortcut to toggle voice recording via Ctrl+Space / Win+Space
  useEffect(() => {
    const handleVoiceShortcut = (event: KeyboardEvent) => {
      if ((event.key === ' ' || event.code === 'Space') && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        if (!isRunning && !isTranscribing) {
          toggleRecording();
        }
      }
    };
    window.addEventListener('keydown', handleVoiceShortcut);
    return () => {
      window.removeEventListener('keydown', handleVoiceShortcut);
    };
  }, [isRunning, isTranscribing, isRecording]);

  // Setup native Tauri and web drag-and-drop listener
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    getCurrentWindow()
      .onDragDropEvent((event) => {
        if (event.payload.type === 'enter' || event.payload.type === 'over') {
          setIsDraggingOver(true);
        } else if (event.payload.type === 'leave') {
          setIsDraggingOver(false);
        } else if (event.payload.type === 'drop') {
          setIsDraggingOver(false);
          const droppedPaths = event.payload.paths || [];
          if (droppedPaths.length > 0) {
            addAttachedFiles(droppedPaths);
          }
        }
      })
      .then((u) => {
        unlisten = u;
      })
      .catch((err) => {
        console.warn('onDragDropEvent failed:', err);
      });

    return () => {
      if (unlisten) unlisten();
    };
  }, []);

  // Agent mode toggle synchronizes AI cursor visibility and active overlay state
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.body.classList.toggle('agent-mode-active', agentModeEnabled);
    }
    void emit('blinky://agent-mode-active', { active: agentModeEnabled });
    if (agentModeEnabled) {
      void showOverlay();
      void setAgentCursorVisibility(true);
      void emit('blinky://agent-cursor-visibility', { visible: true });
    } else {
      // Ensure native cursor restored and AI cursor hidden when exiting agent mode
      void emit('blinky://agent-cursor-visibility', { visible: false });
      void setAgentCursorVisibility(false);
    }
  }, [agentModeEnabled]);

  useEffect(() => {

    const handleUnload = () => {
      void setAgentCursorVisibility(false);
    };
    window.addEventListener('beforeunload', handleUnload);
    return () => {
      window.removeEventListener('beforeunload', handleUnload);
      void setAgentCursorVisibility(false);
    };
  }, []);




  const isVoiceActive = isSpeaking || isRecording || isTtsActive || (isRunning && workflowStartedWithReadbackRef.current);

  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  useEffect(() => {
    void emit('blinky://voice-active', { active: isVoiceActive });
  }, [isVoiceActive]);

  useEffect(() => {
    const unlistenPtt = listen<boolean>('blinky://push-to-talk', (event) => {
      if (event.payload) {
        if (!isRecordingRef.current && !isStartingRecordingRef.current) {
          stopSpeaking();
          void startRecording();
        }
      } else {
        if (isRecordingRef.current) {
          stopRecording();
        }
      }
    });

    return () => {
      unlistenPtt.then((dispose) => dispose());
    };
  }, []);

  // Synchronize wake word detector state with the application state centrally
  useEffect(() => {
    const shouldPause = isRunning || isRecording || isSpeaking || isTtsActive;
    if (shouldPause) {
      void pauseWakeWord();
    } else {
      void resumeWakeWord();
    }
  }, [isRunning, isRecording, isSpeaking, isTtsActive]);


  const updateVoiceProvider = async (newVoiceProvider: 'assemblyai' | 'sarvam') => {
    setVoiceProvider(newVoiceProvider);
    voiceProviderRef.current = newVoiceProvider;
    localStorage.setItem('blinky_voice_provider', newVoiceProvider);
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        newVoiceProvider
      );
    } catch (err) {
      console.error('Failed to save voice provider:', err);
    }
  };

  const updateAssemblyaiApiKey = async (newKey: string) => {
    setAssemblyaiApiKey(newKey);
    assemblyaiApiKeyRef.current = newKey;
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        customModel,
        customApiKey,
        newKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save AssemblyAI API key:', err);
    }
  };

  const updateProvider = async (newProvider: string) => {
    const cleanProvider = newProvider.toLowerCase().trim();
    setProvider(cleanProvider);
    try {
      await saveSettings(
        cleanProvider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save provider:', err);
    }
  };

  const updateShortcut = async (newShortcut: string) => {
    setShortcut(newShortcut);
    try {
      await saveSettings(
        provider,
        newShortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save shortcut:', err);
    }
  };

  const updateSarvamApiKey = async (newKey: string) => {
    setSarvamApiKey(newKey);
    sarvamApiKeyRef.current = newKey;
    try {
      await saveSettings(
        provider,
        shortcut,
        newKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save Sarvam API key:', err);
    }
  };

  const updateGroqApiKey = async (newKey: string) => {
    setGroqApiKey(newKey);
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        newKey,
        deepseekApiKey,
        customUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save Groq API key:', err);
    }
  };

  const updateDeepseekApiKey = async (newKey: string) => {
    setDeepseekApiKey(newKey);
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        newKey,
        customUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save DeepSeek API key:', err);
    }
  };

  const updateCustomUrl = async (newUrl: string) => {
    setCustomUrl(newUrl);
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        newUrl,
        customModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save custom URL:', err);
    }
  };

  const updateCustomModel = async (newModel: string) => {
    setCustomModel(newModel);
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        newModel,
        customApiKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save custom model:', err);
    }
  };

  const updateCustomApiKey = async (newKey: string) => {
    setCustomApiKey(newKey);
    try {
      await saveSettings(
        provider,
        shortcut,
        sarvamApiKey,
        groqApiKey,
        deepseekApiKey,
        customUrl,
        customModel,
        newKey,
        assemblyaiApiKey,
        voiceProvider
      );
    } catch (err) {
      console.error('Failed to save custom API key:', err);
    }
  };

  const handleRecipeDecision = async (save: boolean) => {
    if (!recipePrompt || recipeBusy) return;
    setRecipeBusy(true);
    try {
      await confirmRecipeSave(recipePrompt.recipe_id, save);
    } catch (err) {
      console.error('Failed to confirm recipe save:', err);
    } finally {
      setRecipeBusy(false);
      setRecipePrompt(null);
    }
  };

  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const glowContainerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const toggleButtonRef = useRef<HTMLButtonElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const showStatus = isRunning || status !== defaultStatus;
  const showSummaryBubble = shouldShowSummaryBubble({
    isRunning,
    status,
    defaultStatus,
    steps,
    forceShow: showGuideCompletionSummary,
  });

  // Focus input when open-command event is heard and prewarm connections
  useEffect(() => {
    const focusInput = () => {
      stopSpeaking();
      if (!isRunning && !isRecording) {
        void resumeWakeWord();
      }
      window.setTimeout(() => inputRef.current?.focus(), 60);
    };
    focusInput();

    const unlisten = listen('blinky://open-command', focusInput);
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, [sarvamApiKey]);

  useEffect(() => {
    const unlisten = listen('blinky://wake-word-detected', () => {
      if (!mediaRecorderRef.current) {
        void pauseWakeWord();
        if (!audioCtxRef.current) {
          audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
        } else if (audioCtxRef.current.state === 'suspended') {
          void audioCtxRef.current.resume();
        }
        stopSpeaking();
        void startRecording();
      }
    });
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, [startRecording, stopSpeaking]);

  useEffect(() => {
    const unlisten = listen<TargetClickedPayload>('blinky://target-clicked', (event) => {
      const query = lastQueryRef.current.trim();
      if (!query || isRunning) return;
      const targetText = event.payload.target_text?.trim();
      const instruction = event.payload.instruction?.trim();
      const clickedStep =
        currentGuideStepsRef.current.find(
          (step) => step.instruction?.trim() === instruction && step.target_text?.trim() === targetText,
        ) || {
          instruction: instruction || '',
          target_text: targetText || '',
          match: null,
        };
      if (!shouldCompleteStepOnHighlightClick(clickedStep, query)) {
        void hideOverlay();
        return;
      }
      rememberCompletedStep(targetText, instruction);
      void hideOverlay();
    });
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, [isRunning]);

  // Listen for remote Sentinel power events (Hibernate, Shutdown, Reboot, Lock, Sleep)
  useEffect(() => {
    const unlisten = listen<{ action?: string; message?: string }>('blinky://power-event', (event) => {
      const action = event.payload?.action || 'power action';
      const msg = event.payload?.message || `⚡ Sentinel: Remote ${action} initiated.`;
      setStatus(msg);
      setShowGuideCompletionSummary(true);
    });
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  // Listen for remote mobile queries: executes with native PC Blinky tutor & autopilot pipeline
  useEffect(() => {
    const unlisten = listen<{ requestId: string; query: string }>('blinky://mobile-query', async (event) => {
      const { requestId, query } = event.payload;
      if (!query || !query.trim()) return;
      const cleanQuery = query.trim();
      setQuestion(cleanQuery);
      try {
        await emit('blinky://mobile-status', {
          requestId: requestId || 'unknown',
          status: 'processing',
          data: { message: `Executing '${cleanQuery}' with AI companion...`, percent: 40 },
        });

        await executeTutor(cleanQuery, false, { resetProgress: true });

        const summary = statusRef.current || `Completed: ${cleanQuery}`;
        await emit('blinky://mobile-status', {
          requestId: requestId || 'unknown',
          status: 'success',
          data: {
            response: summary,
            steps: currentGuideStepsRef.current,
          },
        });
      } catch (err: any) {
        await emit('blinky://mobile-status', {
          requestId: requestId || 'unknown',
          status: 'error',
          error: {
            code: 'EXECUTION_ERROR',
            message: err instanceof Error ? err.message : String(err),
            details: '',
          },
        });
      }
    });
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  // Listen for global Enter keypress to auto-advance if the active step is a text-entry step
  useEffect(() => {
    const unlisten = listen('blinky://global-enter', () => {
      // If the Blinky app webview itself has focus, don't auto-complete target app steps
      if (document.hasFocus()) return;

      const query = lastQueryRef.current.trim();
      if (!query || isRunning) return;

      const currentSteps = currentGuideStepsRef.current;
      if (currentSteps.length === 0) return;

      const activeStep = currentSteps[0];
      // Check if it is a text entry step (where shouldCompleteStepOnHighlightClick returns false)
      if (!shouldCompleteStepOnHighlightClick(activeStep)) {
        const targetText = activeStep.target_text?.trim();
        const instruction = activeStep.instruction?.trim();

        rememberCompletedStep(targetText, instruction);

        void hideOverlay();
      }
    });

    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, [isRunning]);



  // Handle clicking outside settings dropdown and window focus change/blur
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        toggleButtonRef.current &&
        !toggleButtonRef.current.contains(event.target as Node)
      ) {
        setShowSettings(false);
      }
    }

    const handleBlur = () => {
      setShowSettings(false);
    };

    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('blur', handleBlur);

    // Listen for Tauri window focus changes to handle global screen clicks
    const unlistenPromise = getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused) {
        setShowSettings(false);
      }
    });

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('blur', handleBlur);
      unlistenPromise.then((dispose) => dispose());
    };
  }, []);

  // Dynamically resize window height based on exact DOM container size to prevent bottom cutoffs when typing long text
  useEffect(() => {
    const formElement = formRef.current;
    if (!formElement) return;

    const resizeWindow = () => {
      const formRect = formElement.getBoundingClientRect();
      let height = formRect.height;

      if (showSettings && dropdownRef.current) {
        const dropdownRect = dropdownRef.current.getBoundingClientRect();
        height = Math.max(height, 52 + dropdownRect.height);
      }

      if (showWaModal) {
        height = Math.max(height, 420);
      }

      const targetHeight = Math.ceil(height + 40);
      void resizeCommandWindow(targetHeight);
    };

    resizeWindow();

    const observer = new ResizeObserver(() => {
      resizeWindow();
    });

    observer.observe(formElement);
    return () => {
      observer.disconnect();
    };
  }, [showSettings, showWaModal, waStatus]);

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuestion(event.target.value);
    const textarea = event.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed && attachedFiles.length === 0) return;
    if (isRunning) return;

    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
    } else if (audioCtxRef.current.state === 'suspended') {
      void audioCtxRef.current.resume();
    }

    void executeTutor(trimmed || 'merge these videos', false);
  }

  let renderWordIndex = 0;

  const highlightText = (node: any): any => {
    if (typeof node === 'string') {
      const words = node.split(/(\s+)/); // keep whitespace
      return words.map((word, idx) => {
        if (!word.trim()) {
          return word;
        }

        const currentIdx = renderWordIndex;
        renderWordIndex++;

        const isCurrent = isTtsActive && currentIdx === activeWordIndex;
        const isSpoken = !isTtsActive || currentIdx < activeWordIndex;

        return (
          <span
            key={currentIdx}
            className={`word-node ${isCurrent ? 'active-speaking-word' : isSpoken ? 'spoken-word' : 'unspoken-word'}`}
          >
            {word}
          </span>
        );
      });
    }

    if (Array.isArray(node)) {
      return node.map((child, idx) => <span key={idx}>{highlightText(child)}</span>);
    }

    if (node && isValidElement(node)) {
      const children = (node.props as any).children;
      if (children) {
        return cloneElement(node, {
          children: highlightText(children)
        } as any);
      }
    }

    return node;
  };

  const markdownComponents = {
    p: ({ children }: any) => {
      return <p className="markdown-p">{highlightText(children)}</p>;
    },
    li: ({ children }: any) => {
      return <li className="markdown-li">{highlightText(children)}</li>;
    },
    ul: ({ children }: any) => {
      return <ul className="markdown-ul">{children}</ul>;
    },
    ol: ({ children }: any) => {
      return <ol className="markdown-ol">{children}</ol>;
    },
    strong: ({ children }: any) => {
      return <strong className="markdown-strong">{highlightText(children)}</strong>;
    },
    em: ({ children }: any) => {
      return <em className="markdown-em">{highlightText(children)}</em>;
    },
    a: (props: any) => {
      return <ExternalMarkdownLink {...props} children={highlightText(props.children)} />;
    },
    h1: ({ children }: any) => {
      return <h1 className="markdown-h1">{highlightText(children)}</h1>;
    },
    h2: ({ children }: any) => {
      return <h2 className="markdown-h2">{highlightText(children)}</h2>;
    },
    h3: ({ children }: any) => {
      return <h3 className="markdown-h3">{highlightText(children)}</h3>;
    },
    h4: ({ children }: any) => {
      return <h4 className="markdown-h4">{highlightText(children)}</h4>;
    },
    h5: ({ children }: any) => {
      return <h5 className="markdown-h5">{highlightText(children)}</h5>;
    },
    h6: ({ children }: any) => {
      return <h6 className="markdown-h6">{highlightText(children)}</h6>;
    },
    table: ({ children }: any) => {
      return (
        <div className="markdown-table-wrapper">
          <table className="markdown-table">{children}</table>
        </div>
      );
    },
    thead: ({ children }: any) => <thead className="markdown-thead">{children}</thead>,
    tbody: ({ children }: any) => <tbody className="markdown-tbody">{children}</tbody>,
    tr: ({ children }: any) => <tr className="markdown-tr">{children}</tr>,
    th: ({ children }: any) => <th className="markdown-th">{highlightText(children)}</th>,
    td: ({ children }: any) => <td className="markdown-td">{highlightText(children)}</td>,
    blockquote: ({ children }: any) => <blockquote className="markdown-blockquote">{children}</blockquote>,
    hr: () => <hr className="markdown-hr" />,
    code: ({ inline, className, children, ...props }: any) => {
      const isInline = inline ?? !String(children).includes('\n');
      return isInline ? (
        <code className="markdown-inline-code" {...props}>{children}</code>
      ) : (
        <pre className="markdown-pre"><code className="markdown-code-block" {...props}>{children}</code></pre>
      );
    },
  };

  async function startDrag() {
    await getCurrentWindow().startDragging();
  }

  return (
    <main className="command-window">
      <form
        ref={formRef}
        className="command-popup command-mini"
        onSubmit={submit}
      >
        <div
          className="resize-handle resize-handle-left"
          onPointerDown={(e) => startResize(e, 'left')}
          onPointerMove={handleResize}
          onPointerUp={stopResize}
          onPointerCancel={stopResize}
        />
        <div
          className="resize-handle resize-handle-right"
          onPointerDown={(e) => startResize(e, 'right')}
          onPointerMove={handleResize}
          onPointerUp={stopResize}
          onPointerCancel={stopResize}
        />
        <div
          className="command-header"
          data-tauri-drag-region
          onMouseDown={(event) => {
            // Only start dragging if not clicking a button, settings options, or interactive items
            const target = event.target as HTMLElement;
            if (!target.closest('button') && !target.closest('.command-settings-dropdown')) {
              void startDrag();
            }
          }}
        >
          <div className="command-icon">
            <Sparkles size={18} />
          </div>

          <div className="command-top-hint" data-tauri-drag-region>
            Blinky app <span className="keys">Ctrl + Shift + {shortcut === 'Space' ? 'Space' : 'Enter'}</span>
          </div>

          <div className="command-actions">
            <button
              ref={toggleButtonRef}
              type="button"
              className={`icon-action command-settings-toggle ${showSettings ? 'active' : ''}`}
              aria-label="Settings"
              onClick={() => setShowSettings(!showSettings)}
            >
              <Settings size={18} />
            </button>
            <button
              type="button"
              className="icon-action"
              aria-label="Minimize"
              onClick={() => getCurrentWindow().minimize()}
            >
              <Minus size={18} />
            </button>
            <button
              type="button"
              className="icon-action"
              aria-label="Close"
              onClick={() => getCurrentWindow().hide()}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Google-Style Dropdown Menu */}
        {showSettings && (
          <div ref={dropdownRef} className="command-settings-dropdown">
            <div className="dropdown-section">
              <h4>Change Model</h4>
              <div className="dropdown-options">
                {(['groq', 'ollama', 'deepseek', 'mimo', 'custom'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    className={`dropdown-option ${provider.toLowerCase().trim() === p ? 'active' : ''}`}
                    onClick={() => updateProvider(p)}
                  >
                    <span>{p === 'custom' ? 'Custom (OpenAI-compatible)' : p.charAt(0).toUpperCase() + p.slice(1)}</span>
                    {provider.toLowerCase().trim() === p && <Check size={14} className="active-dot" />}
                  </button>
                ))}
              </div>
            </div>

            <div className="dropdown-section">
              <h4>Shortcut Key</h4>
              <div className="dropdown-options">
                <button
                  type="button"
                  className={`dropdown-option ${shortcut === 'Enter' ? 'active' : ''}`}
                  onClick={() => updateShortcut('Enter')}
                >
                  <span>Ctrl + Shift + Enter</span>
                  {shortcut === 'Enter' && <Check size={14} className="active-dot" />}
                </button>
                <button
                  type="button"
                  className={`dropdown-option ${shortcut === 'Space' ? 'active' : ''}`}
                  onClick={() => updateShortcut('Space')}
                >
                  <span>Ctrl + Win + Space</span>
                  {shortcut === 'Space' && <Check size={14} className="active-dot" />}
                </button>
              </div>
            </div>

            {provider.toLowerCase().trim() === 'groq' && (
              <div className="dropdown-section">
                <h4>Groq API Key</h4>
                <input
                  type="password"
                  className="settings-input"
                  value={groqApiKey}
                  onChange={(e) => updateGroqApiKey(e.target.value)}
                  placeholder="Paste API Key..."
                />
              </div>
            )}

            {provider.toLowerCase().trim() === 'deepseek' && (
              <div className="dropdown-section">
                <h4>DeepSeek API Key</h4>
                <input
                  type="password"
                  className="settings-input"
                  value={deepseekApiKey}
                  onChange={(e) => updateDeepseekApiKey(e.target.value)}
                  placeholder="Paste API Key..."
                />
              </div>
            )}

            {provider.toLowerCase().trim() === 'custom' && (
              <>
                <div className="dropdown-section">
                  <h4>Custom API URL</h4>
                  <input
                    type="text"
                    className="settings-input"
                    value={customUrl}
                    onChange={(e) => updateCustomUrl(e.target.value)}
                    placeholder="https://opencode.ai/zen/v1"
                  />
                </div>
                <div className="dropdown-section">
                  <h4>Model</h4>
                  <input
                    type="text"
                    className="settings-input"
                    value={customModel}
                    onChange={(e) => updateCustomModel(e.target.value)}
                    placeholder="minimax-m3"
                  />
                </div>
                <div className="dropdown-section">
                  <h4>Custom API Key</h4>
                  <input
                    type="password"
                    className="settings-input"
                    value={customApiKey}
                    onChange={(e) => updateCustomApiKey(e.target.value)}
                    placeholder="Paste API Key..."
                  />
                </div>
              </>
            )}

            <div className="dropdown-section">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                <h4>Voice Provider</h4>
                <span style={{ fontSize: '10px', background: 'rgba(255, 110, 95, 0.2)', color: '#ff8b6a', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                  {voiceProvider === 'assemblyai' ? 'Universal-3 Pro' : 'Indic Voice'}
                </span>
              </div>
              <div className="voice-provider-tabs">
                <button
                  type="button"
                  className={`voice-provider-tab ${voiceProvider === 'assemblyai' ? 'active aai' : ''}`}
                  onClick={() => void updateVoiceProvider('assemblyai')}
                >
                  <span>⚡ AssemblyAI</span>
                </button>
                <button
                  type="button"
                  className={`voice-provider-tab ${voiceProvider === 'sarvam' ? 'active' : ''}`}
                  onClick={() => void updateVoiceProvider('sarvam')}
                >
                  <span>Sarvam AI</span>
                </button>
              </div>
            </div>

            {voiceProvider === 'assemblyai' ? (
              <div className="dropdown-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                  <h4>AssemblyAI API Key</h4>
                  <span style={{ fontSize: '9.5px', color: 'rgba(255, 255, 255, 0.5)' }}>Universal-3 Pro</span>
                </div>
                <input
                  type="password"
                  className="settings-input"
                  value={assemblyaiApiKey}
                  onChange={(e) => void updateAssemblyaiApiKey(e.target.value)}
                  placeholder="Paste AssemblyAI API Key..."
                />
                <div className="voice-mode-selector">
                  <button
                    type="button"
                    className={`voice-mode-btn ${assemblyaiVoiceMode === 'agent' ? 'active' : ''}`}
                    onClick={() => setAssemblyaiVoiceMode('agent')}
                    title="Real-time voice agent with VAD and tool calling"
                  >
                    Voice Agent API
                  </button>
                  <button
                    type="button"
                    className={`voice-mode-btn ${assemblyaiVoiceMode === 'realtime_stt' ? 'active' : ''}`}
                    onClick={() => setAssemblyaiVoiceMode('realtime_stt')}
                    title="Sub-second streaming speech-to-text"
                  >
                    Realtime STT API
                  </button>
                </div>
              </div>
            ) : (
              <div className="dropdown-section">
                <h4>Sarvam AI API Key</h4>
                <input
                  type="password"
                  className="settings-input"
                  value={sarvamApiKey}
                  onChange={(e) => void updateSarvamApiKey(e.target.value)}
                  placeholder="Paste Sarvam API Key..."
                />
              </div>
            )}

            {transportInfo?.mode === 'release' && transportInfo.certificate_pin && (
              <div className="dropdown-section">
                <h4>Mobile Release Link</h4>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary, #9ca3af)', lineHeight: 1.45 }}>
                  <div>Enter this certificate pin and your BLINKY_REMOTE_TOKEN in the mobile release build.</div>
                  <code style={{ display: 'block', marginTop: '8px', wordBreak: 'break-all', color: '#fff' }}>
                    {transportInfo.certificate_pin}
                  </code>
                  <button
                    type="button"
                    className="dropdown-option"
                    style={{ marginTop: '8px', width: '100%' }}
                    onClick={() => void navigator.clipboard?.writeText(transportInfo.certificate_pin || '')}
                  >
                    Copy certificate pin
                  </button>
                </div>
              </div>
            )}

            <div className="dropdown-section">
              <h4>WhatsApp</h4>
              <div className="dropdown-options">
                <button
                  type="button"
                  className="dropdown-option wa-dropdown-btn"
                  onClick={() => {
                    setShowWaModal(true);
                    setShowSettings(false);
                  }}
                >
                  <span>Link / Connection Status</span>
                  <div className={`wa-indicator-dot ${waStatus === 'connected' ? 'connected' : 'disconnected'}`} />
                </button>
              </div>
            </div>

            <div className="dropdown-section">
              <h4>Shortcuts & Voice</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', color: 'var(--text-secondary, #9ca3af)', marginTop: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>Toggle App</span>
                  <code style={{ background: 'rgba(255, 255, 255, 0.08)', padding: '2px 6px', borderRadius: '4px', color: '#fff', fontSize: '11px' }}>Ctrl + Shift + {shortcut}</code>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>Push-to-Talk (Hold to speak)</span>
                  <code style={{ background: 'rgba(255, 139, 106, 0.15)', color: 'var(--accent-strong, #ff8b6a)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>Win + Space</code>
                </div>
              </div>
            </div>

            <div className="dropdown-section dropdown-about">
              <span>Theme: <strong>Ember</strong></span>
              <span>About: <strong>v1.0.0</strong></span>
            </div>
          </div>
        )}


        {/* Workflow-save prompt (agent loop completed a task) */}
        {recipePrompt && (
          <div className="recipe-prompt-banner">
            <div className="recipe-prompt-title">
              <Sparkles size={14} />
              <span>Save this workflow?</span>
            </div>
            <div className="recipe-prompt-preview">
              {recipePrompt.preview.length > 0
                ? recipePrompt.preview.slice(0, 6).map((step, i) => (
                    <span key={i} className="recipe-prompt-step">{step}</span>
                  ))
                : <span className="recipe-prompt-step">No reusable steps</span>}
            </div>
            <div className="recipe-prompt-actions">
              <button type="button" className="recipe-prompt-btn primary" disabled={recipeBusy} onClick={() => handleRecipeDecision(true)}>
                <Check size={13} /> Save
              </button>
              <button type="button" className="recipe-prompt-btn" disabled={recipeBusy} onClick={() => handleRecipeDecision(false)}>
                <X size={13} /> Discard
              </button>
            </div>
          </div>
        )}

        {isDraggingOver && (
          <div className="command-dropzone-overlay">
            <div className="command-dropzone-icon-row">
              <Film size={24} />
              <ImageIcon size={24} />
              <Music size={24} />
            </div>
            <span className="command-dropzone-text">Drop videos or images to reference in AiCut</span>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="video/*,image/*,audio/*"
          style={{ display: 'none' }}
          onChange={handleFileInputChange}
        />

        <div
          className="command-stack"
          onDragOver={(e) => { e.preventDefault(); setIsDraggingOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDraggingOver(false); }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDraggingOver(false);
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
              const paths: string[] = [];
              for (let i = 0; i < e.dataTransfer.files.length; i++) {
                const f = e.dataTransfer.files[i];
                const p = (f as any).path || f.name;
                if (p) paths.push(p);
              }
              addAttachedFiles(paths);
            }
          }}
        >
          <div className="command-input" onClick={() => inputRef.current?.focus()}>
            {attachedFiles.length > 0 && (
              <div className="command-attachments-tray">
                {attachedFiles.map((file) => (
                  <div key={file.path} className={`command-attachment-chip ${file.type}`} title={file.path}>
                    {file.previewUrl ? (
                      <img src={file.previewUrl} alt="" className="command-attachment-thumb" />
                    ) : file.type === 'video' ? (
                      <Film size={13} />
                    ) : file.type === 'audio' ? (
                      <Music size={13} />
                    ) : (
                      <ImageIcon size={13} />
                    )}
                    <span className="command-attachment-name">{file.name}</span>
                    <button
                      type="button"
                      className="command-attachment-remove"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeAttachedFile(file.path);
                      }}
                      title="Remove file"
                    >
                      <X size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <textarea
              ref={inputRef}
              rows={1}
              value={question}
              onChange={handleInputChange}
              placeholder={
                isRecording
                  ? assemblyaiApiKey || assemblyaiApiKeyRef.current
                    ? assemblyaiVoiceMode === 'agent'
                      ? "⚡ AssemblyAI Voice Agent listening... (Win+Space)"
                      : "🎙️ AssemblyAI Realtime STT listening... (Win+Space)"
                    : "Listening... click mic to stop (Win+Space)"
                  : isTranscribing
                  ? "Transcribing voice with Universal-3 Pro..."
                  : assemblyaiApiKey || assemblyaiApiKeyRef.current
                  ? `Ask anything or speak (Win+Space) • AssemblyAI ${assemblyaiVoiceMode === 'agent' ? 'Voice Agent' : 'Realtime STT'}`
                  : "Ask anything... (Win+Space to speak)"
              }
              disabled={isTranscribing}
              autoFocus
              onKeyDown={(event) => {
                if ((event.key === ' ' || event.code === 'Space') && event.metaKey) {
                  event.preventDefault();
                  if (!isRunning && !isTranscribing) {
                    toggleRecording();
                  }
                  return;
                }
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submit(event);
                }
              }}
            />
            <div className="command-input-actions">
              <div className="command-input-actions-left">
                {(assemblyaiApiKey || assemblyaiApiKeyRef.current) && (
                  <button
                    type="button"
                    className={`command-aai-btn ${assemblyaiVoiceMode === 'agent' ? 'agent-mode' : 'stt-mode'}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setAssemblyaiVoiceMode(prev => prev === 'agent' ? 'realtime_stt' : 'agent');
                    }}
                    disabled={isRunning || isTranscribing}
                    title={`AssemblyAI Mode: ${assemblyaiVoiceMode === 'agent' ? 'Voice Agent API (Universal-3 Pro + Tool Calling)' : 'Realtime STT API (Universal-3 Pro)'}. Click to switch.`}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '3px 8px',
                      borderRadius: '12px',
                      border: '1px solid rgba(59, 130, 246, 0.4)',
                      background: assemblyaiVoiceMode === 'agent' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(168, 85, 247, 0.2)',
                      color: assemblyaiVoiceMode === 'agent' ? '#93c5fd' : '#d8b4fe',
                      cursor: 'pointer'
                    }}
                  >
                    <Sparkles size={12} />
                    <span>{assemblyaiVoiceMode === 'agent' ? 'AAI Voice Agent' : 'AAI Realtime STT'}</span>
                  </button>
                )}
                <button
                  type="button"
                  className={`command-attach-btn ${attachedFiles.length > 0 ? 'has-attachments' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                  disabled={isRunning || isTranscribing}
                  title="Attach video or image reference (or drag & drop)"
                >
                  <Paperclip size={16} />
                </button>
                <button
                  type="button"
                  className={`command-websearch-btn ${webSearchEnabled ? 'active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    const nextEnabled = !webSearchEnabled;
                    setWebSearchEnabled(nextEnabled);
                    if (nextEnabled) {
                      setAgentModeEnabled(false);
                    }
                  }}
                  disabled={isRunning || isTranscribing}
                  title="Toggle Web Search"
                >
                  <Globe size={16} />
                </button>
                <button
                  type="button"
                  className={`command-agent-btn ${agentModeEnabled ? 'active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    const nextEnabled = !agentModeEnabled;
                    setAgentModeEnabled(nextEnabled);
                    if (nextEnabled) {
                      setWebSearchEnabled(false);
                    }
                  }}
                  disabled={isRunning || isTranscribing}
                  title="Toggle Agent Automation"
                >
                  <Bot size={16} />
                </button>
              </div>
              <div className="command-input-actions-right">
                <button
                  type="button"
                  className={`command-mic-btn ${isRecording ? 'recording' : ''} ${isTranscribing ? 'loading' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleRecording();
                  }}
                  disabled={isRunning || isTranscribing}
                  title={isRecording ? "Stop recording (Win+Space)" : "Record voice command (Win+Space)"}
                >
                  {isTranscribing ? (
                    <Loader2 className="spin" size={16} />
                  ) : isRecording ? (
                    <span className="mic-record-indicator" />
                  ) : (
                    <Mic size={16} />
                  )}
                </button>
                <button
                  className={`command-send ${isRunning ? 'stopping' : ''}`}
                  type={isRunning ? 'button' : 'submit'}
                  disabled={isTranscribing || (!isRunning && question.trim().length === 0)}
                  onClick={(event) => {
                    if (!isRunning) return;
                    event.preventDefault();
                    event.stopPropagation();
                    stopCurrentRun();
                  }}
                  title={isRunning ? 'Stop thinking' : 'Send'}
                >
                  {isRunning ? <Square size={14} fill="currentColor" /> : <ArrowUp size={18} />}
                </button>
              </div>
            </div>
          </div>

          {(webSearchEnabled || agentModeEnabled) && isRunning && (
            <div className="command-progress-bar-container">
              <div className="command-progress-bar-fill" />
              <div className="command-progress-status-text">
                {agentModeEnabled ? <Bot size={12} className="spin" /> : <Globe size={12} className="spin" />}
                <span>{agentModeEnabled ? 'Agent Automation Active...' : 'Web Intelligence Search Active...'}</span>
              </div>
            </div>
          )}

          {showStatus && (
            <div className="command-result-container">
              {showSummaryBubble && (
                <div className="command-summary-bubble">
                  <Sparkles size={14} className="summary-sparkle" />
                  <div className="command-summary-text-container">
                    <span className="command-status">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents as any}>
                        {preprocessMarkdown(status)}
                      </ReactMarkdown>
                    </span>
                  </div>
                </div>
              )}

              {steps.length > 0 && (
                <div className="command-steps-panel">
                  <h3>Action Guide</h3>
                  <ul className={`steps ${steps.length === 1 ? 'steps-single' : ''}`}>
                    {steps.map((step, idx) => (
                      <li
                        className={[
                          idx === steps.length - 1 ? 'guide-step-current' : 'guide-step-completed',
                          steps.length === 1 ? 'guide-step-single' : '',
                        ].filter(Boolean).join(' ')}
                        key={`${step.step || idx}-${step.instruction}-${step.target_text}`}
                      >
                        {steps.length > 1 && <span>{idx + 1}</span>}
                        <div>
                          <p>{step.instruction}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </form>

      {showWaModal && (
        <div className="wa-modal-backdrop" onClick={() => setShowWaModal(false)}>
          <div className="wa-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="wa-modal-header">
              <h3>WhatsApp Connection</h3>
              <button
                type="button"
                className="wa-modal-close"
                onClick={() => setShowWaModal(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="wa-modal-content">
              {waStatus === 'loading' && (
                <div className="wa-disconnected">
                  <div className="wa-loader">
                    <Loader2 className="spin" size={16} />
                    <span>Loading WhatsApp status...</span>
                  </div>
                  <button
                    type="button"
                    className="wa-btn wa-btn-logout"
                    onClick={logoutWhatsApp}
                    disabled={isWaActionLoading}
                  >
                    {isWaActionLoading ? <Loader2 className="spin" size={14} /> : 'Logout WhatsApp'}
                  </button>
                </div>
              )}

              {waStatus === 'disconnected' && (
                <div className="wa-disconnected">
                  <p className="wa-help-text">Connect to summarize group or direct chats using AI commands.</p>
                  <button
                    type="button"
                    className="wa-btn wa-btn-connect"
                    onClick={() => connectWhatsApp()}
                    disabled={isWaActionLoading}
                  >
                    {isWaActionLoading ? <Loader2 className="spin" size={14} /> : 'Connect WhatsApp'}
                  </button>
                </div>
              )}

              {waStatus === 'qr' && (
                <div className="wa-qr-container">
                  <p className="wa-scan-instruction">Scan this QR code with WhatsApp Linked Devices:</p>
                  <div className="wa-qr-canvas-wrapper">
                    <canvas ref={waCanvasRef} className="wa-qr-canvas" />
                    {isWaActionLoading && (
                      <div className="wa-qr-overlay">
                        <Loader2 className="spin" size={24} />
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className="wa-btn wa-btn-cancel"
                    onClick={logoutWhatsApp}
                    disabled={isWaActionLoading}
                  >
                    Cancel Connection
                  </button>
                </div>
              )}

              {waStatus === 'connected' && (
                <div className="wa-connected">
                  <div className="wa-status-badge">
                    <Check size={14} className="wa-check-icon" />
                    <span>WhatsApp Connected</span>
                  </div>
                  <button
                    type="button"
                    className="wa-btn wa-btn-logout"
                    onClick={logoutWhatsApp}
                    disabled={isWaActionLoading}
                  >
                    {isWaActionLoading ? <Loader2 className="spin" size={14} /> : 'Disconnect Account'}
                  </button>
                </div>
              )}

              {waStatus === 'error' && (
                <div className="wa-error-container">
                  <p className="wa-error-msg">{waError || 'An error occurred'}</p>
                  <button
                    type="button"
                    className="wa-btn wa-btn-retry"
                    onClick={() => connectWhatsApp()}
                    disabled={isWaActionLoading}
                  >
                    Retry Connection
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
