import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ArrowUp, Loader2, Minus, Sparkles, X, Settings, Check } from 'lucide-react';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { runTutor, showOverlay } from './lib/tauri';

export function CommandBar() {
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const defaultStatus = 'Ask anything on your screen';
  const [status, setStatus] = useState(defaultStatus);
  const [steps, setSteps] = useState<any[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [shortcut, setShortcut] = useState('Enter');

  const inputRef = useRef<HTMLInputElement | null>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const toggleButtonRef = useRef<HTMLButtonElement | null>(null);

  const showStatus = isRunning || status !== defaultStatus;

  useEffect(() => {
    const focusInput = () => window.setTimeout(() => inputRef.current?.focus(), 60);
    focusInput();

    const unlisten = listen('clicky://open-command', focusInput);
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

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

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

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
      await showOverlay();
      await currentWindow.setFocus();
      setStatus(result.summary);
      setSteps(result.steps || []);
      setQuestion('');
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
      <form className="command-popup command-mini" onSubmit={submit}>
        <div 
          className="command-header" 
          data-tauri-drag-region
          onMouseDown={(event) => {
            // Only start dragging if not clicking a button
            if ((event.target as HTMLElement).tagName !== 'BUTTON' && (event.target as HTMLElement).parentElement?.tagName !== 'BUTTON') {
              event.preventDefault();
              void startDrag();
            }
          }}
        >
          <div className="command-icon">
            <Sparkles size={18} />
          </div>
          
          <div className="command-top-hint" data-tauri-drag-region>
            Clicky app <span className="keys">Ctrl + Shift + Enter</span>
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
                  onClick={() => setProvider('groq')}
                >
                  <span>Groq</span>
                  {provider === 'groq' && <Check size={14} className="active-dot" />}
                </button>
                <button
                  type="button"
                  className={`dropdown-option ${provider === 'ollama' ? 'active' : ''}`}
                  onClick={() => setProvider('ollama')}
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
                  onClick={() => setShortcut('Enter')}
                >
                  <span>Ctrl + Shift + Enter</span>
                  {shortcut === 'Enter' && <Check size={14} className="active-dot" />}
                </button>
                <button
                  type="button"
                  className={`dropdown-option ${shortcut === 'Space' ? 'active' : ''}`}
                  onClick={() => setShortcut('Space')}
                >
                  <span>Ctrl + Shift + Space</span>
                  {shortcut === 'Space' && <Check size={14} className="active-dot" />}
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
          <div className="command-input">
            <input
              ref={inputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask anything..."
              autoFocus
            />
            <button className="command-send" type="submit" disabled={isRunning || question.trim().length === 0}>
              {isRunning ? <Loader2 className="spin" size={16} /> : <ArrowUp size={16} />}
            </button>
          </div>

          {showStatus && (
            <div className="command-result-container">
              <div className="command-summary-bubble">
                <Sparkles size={14} className="summary-sparkle" />
                <span className="command-status">{status}</span>
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
                          {step.target_text && (
                            <small className="target-text-badge">
                              Target: <code>{step.target_text}</code>
                            </small>
                          )}
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
