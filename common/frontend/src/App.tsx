import { emit, listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ArrowUp, Loader2, Minus, Sparkles, X, Settings, Check, QrCode } from 'lucide-react';
import { FormEvent, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import QRCode from 'qrcode';
import { linkCitationMarkers } from './lib/citations';
import { runTutor, showOverlay, resizeCommandWindow, getSettings, saveSettings, resizeAndMoveCommandWindow, openUrl } from './lib/tauri';

export function App() {
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
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
  const [showSettings, setShowSettings] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [shortcut, setShortcut] = useState('Enter');
  const [sarvamApiKey, setSarvamApiKey] = useState('');
  const [groqApiKey, setGroqApiKey] = useState('');
  const [deepseekApiKey, setDeepseekApiKey] = useState('');

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
        setWaStatus('disconnected');
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

  // Keep WhatsApp status fresh so the UI reflects startup state without user action.
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
            dark: '#090D16',
            light: '#ffffff'
          }
        },
        (error) => {
          if (error) console.error('Failed to render QR Code:', error);
        }
      );
    }
  }, [waStatus, waQr]);

  // Load settings on mount
  useEffect(() => {
    getSettings()
      .then((settings) => {
        setProvider(settings.provider);
        setShortcut(settings.shortcut);
        setSarvamApiKey(settings.sarvam_api_key || '');
        setGroqApiKey(settings.groq_api_key || '');
        setDeepseekApiKey(settings.deepseek_api_key || '');
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
    const cleanProvider = newProvider.toLowerCase().trim();
    setProvider(cleanProvider);
    try {
      await saveSettings(cleanProvider, shortcut, sarvamApiKey, groqApiKey, deepseekApiKey);
    } catch (err) {
      console.error('Failed to save provider:', err);
    }
  };

  const updateShortcut = async (newShortcut: string) => {
    setShortcut(newShortcut);
    try {
      await saveSettings(provider, newShortcut, sarvamApiKey, groqApiKey, deepseekApiKey);
    } catch (err) {
      console.error('Failed to save shortcut:', err);
    }
  };

  const updateSarvamApiKey = async (newKey: string) => {
    setSarvamApiKey(newKey);
    try {
      await saveSettings(provider, shortcut, newKey, groqApiKey, deepseekApiKey);
    } catch (err) {
      console.error('Failed to save Sarvam API key:', err);
    }
  };

  const updateGroqApiKey = async (newKey: string) => {
    setGroqApiKey(newKey);
    try {
      await saveSettings(provider, shortcut, sarvamApiKey, newKey, deepseekApiKey);
    } catch (err) {
      console.error('Failed to save Groq API key:', err);
    }
  };

  const updateDeepseekApiKey = async (newKey: string) => {
    setDeepseekApiKey(newKey);
    try {
      await saveSettings(provider, shortcut, sarvamApiKey, groqApiKey, newKey);
    } catch (err) {
      console.error('Failed to save DeepSeek API key:', err);
    }
  };

  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const toggleButtonRef = useRef<HTMLButtonElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const showStatus = isRunning || status !== defaultStatus;

  // Focus input when open-command event is heard
  useEffect(() => {
    const focusInput = () => window.setTimeout(() => inputRef.current?.focus(), 60);
    focusInput();

    const unlisten = listen('blinky://open-command', focusInput);
    return () => {
      unlisten.then((dispose) => dispose());
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
    if (!trimmed || isRunning) return;

    setIsRunning(true);
    setStatus('Reading the screen...');
    setSteps([]);
    const currentWindow = getCurrentWindow();
    try {
      const result = await runTutor(trimmed);
      await emit('blinky://guidance', result);
      await showOverlay();
      await currentWindow.setFocus();
      setStatus(result.summary);
      setSteps(result.steps || []);
      setQuestion('');
      if (inputRef.current) {
        inputRef.current.style.height = 'auto'; // Reset textarea height on submit
      }
    } catch (error) {
      await currentWindow.setFocus();
      setStatus(error instanceof Error ? error.message : String(error));
      setSteps([]);
    } finally {
      setIsRunning(false);
    }
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
              <select
                className="settings-input settings-select"
                value={provider}
                onChange={(e) => updateProvider(e.target.value)}
              >
                <option value="groq">Groq</option>
                <option value="ollama">Ollama</option>
                <option value="deepseek">DeepSeek</option>
                <option value="mimo">MiMo</option>
              </select>
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
              placeholder="Ask anything..."
              autoFocus
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submit(event);
                }
              }}
            />
            <button className="command-send" type="submit" disabled={isRunning || question.trim().length === 0}>
              {isRunning ? <Loader2 className="spin" size={16} /> : <ArrowUp size={16} />}
            </button>
          </div>

          {showStatus && (
            <div className="command-result-container">
              <div className="command-summary-bubble">
                <Sparkles size={14} className="summary-sparkle" />
                <span className="command-status">
                  <ReactMarkdown
                    components={{
                      a: ({ node, href, children, ...props }) => (
                        <a
                          href={href}
                          className={
                            /^\d+$/.test(Array.isArray(children) ? children.join('') : String(children || ''))
                              ? 'citation-link'
                              : undefined
                          }
                          {...props}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            if (href) {
                              void openUrl(href);
                            }
                          }}
                        >
                          {/^\d+$/.test(Array.isArray(children) ? children.join('') : String(children || ''))
                            ? `[${Array.isArray(children) ? children.join('') : String(children || '')}]`
                            : children}
                        </a>
                      )
                    }}
                  >
                    {linkCitationMarkers(status)}
                  </ReactMarkdown>
                </span>
              </div>

              {steps.length > 0 && (
                <div className="command-steps-panel">
                  <h3>Action Guide</h3>
                  <ul className="steps">
                    {steps.map((step, idx) => (
                      <li key={step.step || idx}>
                        <span>{step.step || (idx + 1)}</span>
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
                    onClick={connectWhatsApp}
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
                    onClick={connectWhatsApp}
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
