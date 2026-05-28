import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ArrowUp, Loader2, Minus, Sparkles, X } from 'lucide-react';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { runTutor, showOverlay } from './lib/tauri';

export function CommandBar() {
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const defaultStatus = 'Ask anything on your screen';
  const [status, setStatus] = useState(defaultStatus);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const showStatus = isRunning || status !== defaultStatus;

  useEffect(() => {
    const focusInput = () => window.setTimeout(() => inputRef.current?.focus(), 60);
    focusInput();

    const unlisten = listen('clicky://open-command', focusInput);
    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isRunning) return;

    setIsRunning(true);
    setStatus('Reading the screen...');
    const currentWindow = getCurrentWindow();
    try {
      const result = await runTutor(trimmed);
      await showOverlay();
      await currentWindow.setFocus();
      setStatus(result.summary);
      setQuestion('');
    } catch (error) {
      await currentWindow.setFocus();
      setStatus(error instanceof Error ? error.message : String(error));
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
          <div className="command-meta">
            {showStatus && <span className="command-status">{status}</span>}
          </div>
        </div>
      </form>
    </main>
  );
}
