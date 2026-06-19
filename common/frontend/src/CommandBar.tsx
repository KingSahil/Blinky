import { emit, listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ArrowUp, Bot, Loader2, Minus, Sparkles, X, Settings, Check, Mic, Volume2, Globe, Square } from 'lucide-react';
import { AnchorHTMLAttributes, FormEvent, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { runAutopilotLoop, extractTextToType, shouldPressEnterAfterTyping, isScrollAction, getScrollDirection } from './lib/autopilot';
import {
  getCurrentGuideSteps,
  getDisplaySteps,
  getHighlightSteps,
  mergeGuideHistory,
  shouldCompleteStepOnHighlightClick,
  shouldShowSummaryBubble,
} from './lib/guidance';
import { runTutor, showOverlay, hideOverlay, resizeCommandWindow, getSettings, saveSettings, resizeAndMoveCommandWindow, clickScreenPoint, openUrl, typeText, scrollAtPoint } from './lib/tauri';
import { linkCitationMarkers } from './lib/citations';
import { buildAudioDataUrl, buildSarvamTtsPayload, buildSpeechContent, getSarvamErrorMessage } from './lib/tts';
import { SarvamSpeechToTextStream, SarvamTextToSpeechStream } from './lib/sarvamStream';
import { AdaptiveTransportManager } from './lib/adaptiveTransport';
import type { TutorConversationMessage, TutorProgress, TutorResult } from './lib/types';

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
      className={isCitation ? 'citation-link' : undefined}
      title={isCitation ? `Open source ${linkText}` : undefined}
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

export function CommandBar() {
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
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
  const [steps, setSteps] = useState<any[]>([]);
  const [showGuideCompletionSummary, setShowGuideCompletionSummary] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [shortcut, setShortcut] = useState('Enter');
  const [sarvamApiKey, setSarvamApiKey] = useState('');
  const [groqApiKey, setGroqApiKey] = useState('');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const lastQueryRef = useRef<string>('');
  const completedTargetsRef = useRef<string[]>([]);
  const completedInstructionsRef = useRef<string[]>([]);
  const currentGuideStepsRef = useRef<any[]>([]);
  const workflowStartedWithReadbackRef = useRef(false);
  const conversationHistoryRef = useRef<TutorConversationMessage[]>([]);
  const runIdRef = useRef(0);
  const cancelledRunIdsRef = useRef<Set<number>>(new Set());
  const latestTranscriptRef = useRef<string>('');

  // WebTransport and WebSocket streaming refs
  const sttStreamRef = useRef<SarvamSpeechToTextStream | null>(null);
  const ttsStreamRef = useRef<SarvamTextToSpeechStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const transportManagerRef = useRef<AdaptiveTransportManager | null>(null);
  const transportStateRef = useRef<'WEBTRANSPORT' | 'WEBSOCKET'>('WEBTRANSPORT');

  // TTS Streaming state
  const speechBufferRef = useRef<string>('');
  const ttsTextQueueRef = useRef<string[]>([]);
  const ttsAudioQueueRef = useRef<string[]>([]);
  const isFetchingTtsRef = useRef<boolean>(false);
  const isPlayingTtsRef = useRef<boolean>(false);

  const rememberCompletedStep = (targetText?: string, instruction?: string) => {
    const cleanTarget = targetText?.trim();
    const cleanInstruction = instruction?.trim();

    if (cleanTarget && !completedTargetsRef.current.includes(cleanTarget)) {
      completedTargetsRef.current = [...completedTargetsRef.current, cleanTarget];
    }

    if (cleanInstruction && !completedInstructionsRef.current.includes(cleanInstruction)) {
      completedInstructionsRef.current = [...completedInstructionsRef.current, cleanInstruction];
    }
  };

  const stopSpeaking = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
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

    ttsTextQueueRef.current = [];
    ttsAudioQueueRef.current = [];
    isFetchingTtsRef.current = false;
    isPlayingTtsRef.current = false;
    speechBufferRef.current = '';

    setIsSpeaking(false);
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

      if (workflowStartedWithReadbackRef.current) {
        speechBufferRef.current += msg;
        const match = speechBufferRef.current.match(/([^.!?\n]+[.!?\n]+)(\s*|$)/);
        if (match) {
          const sentence = match[1].trim();
          speechBufferRef.current = speechBufferRef.current.substring(match[0].length);
          if (sentence) {
            ttsTextQueueRef.current.push(sentence);
            void processTtsFetchQueueRef.current();
          }
        }
      }
    });

    return () => {
      void unlistenStatus.then((dispose) => dispose());
      void unlistenChunk.then((dispose) => dispose());
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
      } catch {
        const int16Array = new Int16Array(bytes.buffer);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
          float32Array[i] = int16Array[i] / 32768.0;
        }
        audioBuffer = audioCtxRef.current.createBuffer(1, float32Array.length, 16000);
        audioBuffer.getChannelData(0).set(float32Array);
      }

      const source = audioCtxRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioCtxRef.current.destination);

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
    if (isFetchingTtsRef.current || ttsTextQueueRef.current.length === 0 || !sarvamApiKey) return;
    isFetchingTtsRef.current = true;

    while (ttsTextQueueRef.current.length > 0) {
      const text = ttsTextQueueRef.current.shift();
      if (!text) continue;

      try {
        const payload = buildSarvamTtsPayload(text);
        payload.output_audio_codec = 'mp3';

        const res = await fetch('https://api.sarvam.ai/text-to-speech', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'api-subscription-key': sarvamApiKey,
          },
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const data = await res.json();
          const base64Audio = data.audios[0];
          ttsAudioQueueRef.current.push(base64Audio); // push base64 directly
          void processTtsPlayQueue();
        } else {
          console.error('TTS Fetch failed with status:', res.status);
        }
      } catch (err) {
        console.error('Failed to fetch TTS for sentence:', err);
      }
    }
    isFetchingTtsRef.current = false;
  };

  // Update ref so useEffect closure always uses the latest state
  processTtsFetchQueueRef.current = processTtsFetchQueue;

  const processTtsPlayQueue = async () => {
    if (isPlayingTtsRef.current || ttsAudioQueueRef.current.length === 0) return;
    isPlayingTtsRef.current = true;
    setIsSpeaking(true);

    while (ttsAudioQueueRef.current.length > 0) {
      const base64Audio = ttsAudioQueueRef.current.shift();
      if (!base64Audio) continue;

      try {
        if (!audioCtxRef.current) {
          audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
        }
        const ctx = audioCtxRef.current;
        if (ctx.state === 'suspended') {
          await ctx.resume();
        }

        const binary = atob(base64Audio);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }

        let audioBuffer: AudioBuffer;
        try {
          audioBuffer = await ctx.decodeAudioData(bytes.buffer.slice(0));
        } catch (decodeErr) {
          console.warn('decodeAudioData failed, falling back to PCM:', decodeErr);
          const validByteLength = bytes.buffer.byteLength - (bytes.buffer.byteLength % 2);
          const int16Array = new Int16Array(bytes.buffer, 0, validByteLength / 2);
          const float32Array = new Float32Array(int16Array.length);
          for (let i = 0; i < int16Array.length; i++) {
            float32Array[i] = int16Array[i] / 32768.0;
          }
          audioBuffer = ctx.createBuffer(1, float32Array.length, 16000);
          audioBuffer.getChannelData(0).set(float32Array);
        }

        await new Promise<void>((resolve) => {
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(ctx.destination);
          activeSourcesRef.current.push(source);
          
          source.onended = () => {
            activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
            resolve();
          };
          source.start(0);
        });
      } catch (e) {
        console.error('Error decoding/playing TTS chunk:', e);
      }
    }
    
    isPlayingTtsRef.current = false;
    
    if (ttsTextQueueRef.current.length === 0 && !isFetchingTtsRef.current) {
      setIsSpeaking(false);
    }
  };

  const speakText = async (summaryText: string, stepsList: any[], options: { includeSteps?: boolean } = {}) => {
    if (!sarvamApiKey) {
      setStatus('Please set your Sarvam AI API Key in settings first.');
      return;
    }
    
    const speechContent = buildSpeechContent(summaryText, stepsList, options);
    if (!speechContent) return;

    stopSpeaking();

    const sentences = (speechContent.match(/[^.!?\n]+[.!?\n]*/g) || [speechContent])
      .map(s => s.trim())
      .filter(Boolean);

    for (const sentence of sentences) {
      ttsTextQueueRef.current.push(sentence);
    }
    void processTtsFetchQueue();
  };

  const speakResponse = () => {
    if (isSpeaking) {
      stopSpeaking();
    } else if (status && status !== defaultStatus) {
      void speakText(status, steps, { includeSteps: !showGuideCompletionSummary });
    }
  };

  const handleAudioTranscription = async (blob: Blob) => {
    if (!sarvamApiKey) {
      setStatus('Please set your Sarvam AI API Key in settings first.');
      return;
    }
    
    setStatus('Transcribing...');
    try {
      const formData = new FormData();
      formData.append('file', blob, 'query.webm');
      formData.append('model', 'saaras:v3');
      formData.append('language_code', 'en-IN');

      const res = await fetch('https://api.sarvam.ai/speech-to-text', {
        method: 'POST',
        headers: {
          'api-subscription-key': sarvamApiKey,
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
      }
    } catch (err: any) {
      console.error('STT error:', err);
      setStatus(`Transcription failed: ${err.message}`);
    }
  };

  const startRecording = async () => {
    if (!sarvamApiKey) {
      setStatus('Please set your Sarvam AI API Key in settings first.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      (mediaRecorderRef as any).current = mediaRecorder;
      
      const audioChunks: BlobPart[] = [];
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };
      
      // Setup VAD using the shared global AudioContext which was initialized during toggleRecording
      const audioCtx = audioCtxRef.current!;
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      
      let hasSpoken = false;
      let silenceStartTime = 0;
      let silenceTimeoutTriggered = false;
      const SILENCE_THRESHOLD = 0.015;
      const SPEECH_THRESHOLD = 0.035;
      const SILENCE_DURATION_MS = 800;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);

        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);

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
        stream.getTracks().forEach((track) => track.stop());
        try { processor.disconnect(); source.disconnect(); } catch {}
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        void handleAudioTranscription(audioBlob);
      };
      
      mediaRecorder.start();
      setIsRecording(true);
      setStatus('Listening... Click mic to stop.');
      
      // Auto-stop after 10 seconds as a fallback
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          stopRecording();
        }
      }, 10000);
      
    } catch (err) {
      console.error('Error starting audio recording:', err);
      setStatus('Microphone access failed or was denied.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
      mediaRecorderRef.current = null;
      setIsRecording(false);
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
    };
  }

  async function executeTutor(
    queryText: string,
    shouldSpeakAfter: boolean,
    options: TutorRunOptions = {},
  ) {
    if (isRunning) return;
    const runId = runIdRef.current + 1;
    runIdRef.current = runId;

    // Immediately enable streaming TTS if requested
    workflowStartedWithReadbackRef.current = shouldSpeakAfter;

    if (options.resetProgress) {
      completedTargetsRef.current = [];
      completedInstructionsRef.current = [];
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
    
    const currentWindow = getCurrentWindow();
    try {
      let result: TutorResult;
      if (agentModeEnabled) {
        let firstObservation: TutorResult | null = null;
        const autopilot = await runAutopilotLoop({
          maxAttempts: 5,
          observeAfterAction: true,
          observe: async () => {
            if (!firstObservation) {
              firstObservation = await runTutor(queryText, previousQuestion, currentProgress(), conversationHistory, false, true);
              return firstObservation;
            }
            return runTutor(queryText, previousQuestion, currentProgress(), conversationHistory, false, true);
          },
          act: async (point, step) => {
            if (isScrollAction(step.instruction)) {
              const direction = getScrollDirection(step.instruction);
              setStatus(`Autopilot scrolling ${direction}...`);
              rememberCompletedStep(step.target_text, step.instruction);
              await scrollAtPoint(point.x, point.y, direction, 3);
            } else {
              const textToType = extractTextToType(step.instruction);
              if (textToType !== null) {
                setStatus(`Autopilot typing "${textToType}"...`);
                rememberCompletedStep(step.target_text, step.instruction);
                await clickScreenPoint(point.x, point.y);
                await new Promise((resolve) => setTimeout(resolve, 150));
                const pressEnter = shouldPressEnterAfterTyping(step.instruction);
                await typeText(textToType, pressEnter);
              } else {
                setStatus(`Autopilot clicking (${point.x}, ${point.y})...`);
                rememberCompletedStep(step.target_text, step.instruction);
                await clickScreenPoint(point.x, point.y);
              }
            }
          },
        });
        if (autopilot.stopReason === 'complete') {
          result = {
            ...autopilot.finalResult,
            summary: `Autopilot successfully completed the task!`,
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
      } else {
        result = await runTutor(queryText, previousQuestion, currentProgress(), conversationHistory, webSearchEnabled);
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
        lastQueryRef.current = queryText;
      }

      const displaySteps = getDisplaySteps(result.steps || []);
      const currentGuideSteps = getCurrentGuideSteps(displaySteps, currentProgress());
      currentGuideStepsRef.current = currentGuideSteps;
      const hasCompletedProgress =
        completedTargetsRef.current.length > 0 || completedInstructionsRef.current.length > 0;
      const highlightSteps = getHighlightSteps(currentGuideSteps);
      await emit('blinky://guidance', { ...result, steps: currentGuideSteps });
      if (highlightSteps.length > 0) {
        await showOverlay();
      } else {
        await hideOverlay();
      }
      await currentWindow.setFocus();
      setStatus(result.summary);
      const newHistoryEntries: TutorConversationMessage[] = [
        { role: 'student', content: queryText },
        { role: 'blinky', content: result.summary },
      ];
      conversationHistoryRef.current = [
        ...conversationHistoryRef.current,
        ...newHistoryEntries,
      ].slice(-10);
      setShowGuideCompletionSummary(hasCompletedProgress && currentGuideSteps.length === 0 && Boolean(result.summary));
      setSteps((previousSteps) => mergeGuideHistory(previousSteps, currentGuideSteps, currentProgress()));
      setQuestion('');
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
      }
      if (shouldSpeakAfter) {
        if (speechBufferRef.current.trim()) {
          ttsTextQueueRef.current.push(speechBufferRef.current.trim());
          speechBufferRef.current = '';
        }
        
        if (currentGuideSteps.length > 0) {
          const stepText = currentGuideSteps.map((s, i) => `Step ${i + 1}. ${s.instruction}`).join('. ');
          ttsTextQueueRef.current.push(`Steps: ${stepText}`);
        }

        void processTtsFetchQueueRef.current();
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
        setIsRunning(false);
      }
    }
  }

  function stopCurrentRun() {
    const runId = runIdRef.current;
    if (!isRunning || runId === 0) return;
    cancelledRunIdsRef.current.add(runId);
    setIsRunning(false);
    setStatus('Stopped.');
    setSteps([]);
    void hideOverlay();
    stopSpeaking();
  }

  // Load settings on mount
  useEffect(() => {
    getSettings()
      .then((settings) => {
        setProvider(settings.provider);
        setShortcut(settings.shortcut);
        setSarvamApiKey(settings.sarvam_api_key || '');
        setGroqApiKey(settings.groq_api_key || '');
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

  const updateProvider = async (newProvider: string) => {
    setProvider(newProvider);
    try {
      await saveSettings(newProvider, shortcut, sarvamApiKey, groqApiKey);
    } catch (err) {
      console.error('Failed to save provider:', err);
    }
  };

  const updateShortcut = async (newShortcut: string) => {
    setShortcut(newShortcut);
    try {
      await saveSettings(provider, newShortcut, sarvamApiKey, groqApiKey);
    } catch (err) {
      console.error('Failed to save shortcut:', err);
    }
  };

  const updateSarvamApiKey = async (newKey: string) => {
    setSarvamApiKey(newKey);
    try {
      await saveSettings(provider, shortcut, newKey, groqApiKey);
    } catch (err) {
      console.error('Failed to save Sarvam API key:', err);
    }
  };

  const updateGroqApiKey = async (newKey: string) => {
    setGroqApiKey(newKey);
    try {
      await saveSettings(provider, shortcut, sarvamApiKey, newKey);
    } catch (err) {
      console.error('Failed to save Groq API key:', err);
    }
  };

  const inputRef = useRef<HTMLTextAreaElement | null>(null);
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
      window.setTimeout(() => inputRef.current?.focus(), 60);
    };
    focusInput();

    const unlisten = listen('blinky://open-command', focusInput);
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, [sarvamApiKey]);

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
  }, [showSettings]);

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuestion(event.target.value);
    const textarea = event.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isRunning) return;

    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
    } else if (audioCtxRef.current.state === 'suspended') {
      void audioCtxRef.current.resume();
    }

    void executeTutor(trimmed, false);
  }

  async function startDrag() {
    await getCurrentWindow().startDragging();
  }

  return (
    <main className="command-window">
      <form ref={formRef} className="command-popup command-mini" onSubmit={submit}>
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
                <button
                  type="button"
                  className={`dropdown-option ${provider === 'groq' ? 'active' : ''}`}
                  onClick={() => updateProvider('groq')}
                >
                  <span>Groq</span>
                  {provider === 'groq' && <Check size={14} className="active-dot" />}
                </button>
                <button
                  type="button"
                  className={`dropdown-option ${provider === 'ollama' ? 'active' : ''}`}
                  onClick={() => updateProvider('ollama')}
                >
                  <span>Ollama</span>
                  {provider === 'ollama' && <Check size={14} className="active-dot" />}
                </button>
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
                  <span>Ctrl + Shift + Space</span>
                  {shortcut === 'Space' && <Check size={14} className="active-dot" />}
                </button>
              </div>
            </div>

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

            <div className="dropdown-section">
              <h4>Sarvam AI API Key</h4>
              <input
                type="password"
                className="settings-input"
                value={sarvamApiKey}
                onChange={(e) => updateSarvamApiKey(e.target.value)}
                placeholder="Paste API Key..."
              />
            </div>

            <div className="dropdown-section dropdown-about">
              <span>Theme: <strong>Ember</strong></span>
              <span>About: <strong>v1.0.0</strong></span>
            </div>
          </div>
        )}

        <div className="command-stack">
          <div className="command-input" onClick={() => inputRef.current?.focus()}>
            <textarea
              ref={inputRef}
              rows={1}
              value={question}
              onChange={handleInputChange}
              placeholder={isRecording ? "Listening... click mic to stop" : isTranscribing ? "Transcribing voice..." : "Ask anything..."}
              disabled={isTranscribing}
              autoFocus
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submit(event);
                }
              }}
            />
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
            <button
              type="button"
              className={`command-mic-btn ${isRecording ? 'recording' : ''} ${isTranscribing ? 'loading' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                toggleRecording();
              }}
              disabled={isRunning || isTranscribing}
              title={isRecording ? "Stop recording" : "Record voice command"}
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
                      <ReactMarkdown components={{ a: ExternalMarkdownLink }}>{linkCitationMarkers(status)}</ReactMarkdown>
                    </span>
                    {steps.length > 0 && sarvamApiKey && (
                      <button
                        type="button"
                        className={`command-speak-btn ${isSpeaking ? 'speaking' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          speakResponse();
                        }}
                        title={isSpeaking ? "Stop speaking" : "Speak response"}
                      >
                        <Volume2 size={16} />
                      </button>
                    )}
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
    </main>
  );
}
