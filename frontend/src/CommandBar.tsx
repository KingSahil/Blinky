import { emit, listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ArrowUp, Loader2, Minus, Sparkles, X, Settings, Check, Mic, Volume2, Globe } from 'lucide-react';
import { FormEvent, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  getCurrentGuideSteps,
  getDisplaySteps,
  getHighlightSteps,
  getWorkflowContinuationReadback,
  mergeGuideHistory,
  shouldCompleteStepOnHighlightClick,
  shouldShowSummaryBubble,
} from './lib/guidance';
import { runAgentQuery, runTutor, showOverlay, hideOverlay, resizeCommandWindow, getSettings, saveSettings, resizeAndMoveCommandWindow } from './lib/tauri';
import { buildAudioDataUrl, buildSarvamTtsPayload, buildSpeechContent, getSarvamErrorMessage } from './lib/tts';
import type { TutorConversationMessage, TutorProgress } from './lib/types';

interface TargetClickedPayload {
  step?: number;
  target_text?: string;
  instruction?: string;
}

interface TutorRunOptions {
  resetProgress?: boolean;
  preserveStepsDuringRun?: boolean;
}

export function CommandBar() {
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
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

  const stopSpeaking = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    setIsSpeaking(false);
  };

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
      }
    };
  }, []);

  // Listen for real-time status and streaming chunks from python worker
  useEffect(() => {
    let unlistenStatus: Promise<any>;
    let unlistenChunk: Promise<any>;

    unlistenStatus = listen<{ phase: string; message: string }>('blinky://tutor-status', (event) => {
      setStatus(event.payload.message);
    });

    unlistenChunk = listen<{ message: string }>('blinky://tutor-chunk', (event) => {
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
          return event.payload.message;
        }
        return prev + event.payload.message;
      });
    });

    return () => {
      void unlistenStatus.then((dispose) => dispose());
      void unlistenChunk.then((dispose) => dispose());
    };
  }, []);

  const speakText = async (summaryText: string, stepsList: any[], options: { includeSteps?: boolean } = {}) => {
    if (!sarvamApiKey) {
      setStatus('Please set your Sarvam AI API Key in settings first.');
      return;
    }
    
    const speechContent = buildSpeechContent(summaryText, stepsList, options);

    setIsSpeaking(true);
    try {
      const response = await fetch('https://api.sarvam.ai/text-to-speech', {
        method: 'POST',
        headers: {
          'api-subscription-key': sarvamApiKey,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(buildSarvamTtsPayload(speechContent)),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(getSarvamErrorMessage(errorData, response.status));
      }

      const data = await response.json();
      if (!data.audios || data.audios.length === 0) {
        throw new Error('No audio returned from Sarvam AI TTS API.');
      }

      const base64Audio = data.audios[0];
      const audioUrl = buildAudioDataUrl(base64Audio);
      const audio = new Audio(audioUrl);
      
      currentAudioRef.current = audio;
      audio.onended = () => {
        setIsSpeaking(false);
        currentAudioRef.current = null;
      };
      audio.onerror = (e) => {
        console.error('Audio playback error:', e);
        setIsSpeaking(false);
        currentAudioRef.current = null;
      };

      await audio.play();
    } catch (err: any) {
      console.error('TTS error:', err);
      setStatus(`Voice readback failed: ${err.message}`);
      setIsSpeaking(false);
    }
  };

  const speakResponse = () => {
    if (isSpeaking) {
      stopSpeaking();
    } else if (status && status !== defaultStatus) {
      void speakText(status, steps, { includeSteps: !showGuideCompletionSummary });
    }
  };

  const startRecording = async () => {
    if (!sarvamApiKey) {
      setStatus('Please set your Sarvam AI API Key in settings first.');
      return;
    }
    audioChunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const options = { mimeType: 'audio/webm' };
      const recorder = new MediaRecorder(stream, options);
      
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await handleAudioTranscription(audioBlob);
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
      setStatus('Listening... Click mic to stop.');
    } catch (err) {
      console.error('Error starting audio recording:', err);
      setStatus('Microphone access failed or was denied.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      stopSpeaking();
      void startRecording();
    }
  };

  const handleAudioTranscription = async (blob: Blob) => {
    setIsTranscribing(true);
    setStatus('Transcribing speech...');
    
    try {
      const formData = new FormData();
      formData.append('file', blob, 'query.webm');
      formData.append('model', 'saaras:v3');
      formData.append('language_code', 'en-IN');
      
      const response = await fetch('https://api.sarvam.ai/speech-to-text', {
        method: 'POST',
        headers: {
          'api-subscription-key': sarvamApiKey,
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Sarvam STT failed with status ${response.status}`);
      }

      const data = await response.json();
      const text = (data.transcript || '').trim();
      if (!text) {
        throw new Error('Could not understand speech. Please try again.');
      }

      setQuestion(text);
      setStatus(`Searching for: "${text}"`);
      
      void executeTutor(text, true);
    } catch (err: any) {
      console.error('Transcription error:', err);
      setStatus(err.message || 'Failed to transcribe audio.');
    } finally {
      setIsTranscribing(false);
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

    if (options.resetProgress) {
      completedTargetsRef.current = [];
      completedInstructionsRef.current = [];
      currentGuideStepsRef.current = [];
      workflowStartedWithReadbackRef.current = shouldSpeakAfter;
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
      const result = webSearchEnabled
        ? await runAgentQuery(queryText)
        : await runTutor(queryText, previousQuestion, currentProgress(), conversationHistory, webSearchEnabled);
      const isContinuation = !!result.is_continuation;

      if (!isContinuation) {
        completedTargetsRef.current = [];
        completedInstructionsRef.current = [];
        currentGuideStepsRef.current = [];
        workflowStartedWithReadbackRef.current = shouldSpeakAfter;
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
        if (currentGuideSteps.length > 0) {
          void speakText('', [currentGuideSteps[0]], { includeSteps: true });
        } else if (result.summary) {
          void speakText(result.summary, []);
        }
      }
    } catch (error) {
      await currentWindow.setFocus();
      setStatus(error instanceof Error ? error.message : String(error));
      setSteps([]);
    } finally {
      setIsRunning(false);
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

  // Focus input when open-command event is heard
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
  }, []);

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
      if (targetText && !completedTargetsRef.current.includes(targetText)) {
        completedTargetsRef.current = [...completedTargetsRef.current, targetText];
      }
      if (instruction && !completedInstructionsRef.current.includes(instruction)) {
        completedInstructionsRef.current = [...completedInstructionsRef.current, instruction];
      }
      void hideOverlay();
      window.setTimeout(() => {
        void executeTutor(query, getWorkflowContinuationReadback(workflowStartedWithReadbackRef.current), {
          preserveStepsDuringRun: true,
        });
      }, 450);
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

        if (targetText && !completedTargetsRef.current.includes(targetText)) {
          completedTargetsRef.current = [...completedTargetsRef.current, targetText];
        }
        if (instruction && !completedInstructionsRef.current.includes(instruction)) {
          completedInstructionsRef.current = [...completedInstructionsRef.current, instruction];
        }

        void hideOverlay();
        window.setTimeout(() => {
          void executeTutor(query, getWorkflowContinuationReadback(workflowStartedWithReadbackRef.current), {
            preserveStepsDuringRun: true,
          });
        }, 450);
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
                setWebSearchEnabled(!webSearchEnabled);
              }}
              disabled={isRunning || isTranscribing}
              title="Toggle Web Search"
            >
              <Globe size={16} />
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
            <button className="command-send" type="submit" disabled={isRunning || isTranscribing || question.trim().length === 0}>
              {isRunning ? <Loader2 className="spin" size={18} /> : <ArrowUp size={18} />}
            </button>
          </div>

          {webSearchEnabled && isRunning && (
            <div className="command-progress-bar-container">
              <div className="command-progress-bar-fill" />
              <div className="command-progress-status-text">
                <Globe size={12} className="spin" />
                <span>Web Intelligence Search Active...</span>
              </div>
            </div>
          )}

          {showStatus && (
            <div className="command-result-container">
              {showSummaryBubble && (
                <div className="command-summary-bubble">
                  <Sparkles size={14} className="summary-sparkle" />
                  <div className="command-summary-text-container">
                    <span className="command-status"><ReactMarkdown>{status}</ReactMarkdown></span>
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
