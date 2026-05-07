import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { Loader2, MonitorUp, Play, X } from 'lucide-react';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { runTutor, showOverlay } from './lib/tauri';

export function CommandBar() {
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState('Ask anything on your screen');
  const inputRef = useRef<HTMLInputElement | null>(null);

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
    try {
      await getCurrentWindow().hide();
      const result = await runTutor(trimmed);
      await showOverlay();
      setStatus(result.summary);
      setQuestion('');
    } catch (error) {
      await getCurrentWindow().show();
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="command-window">
      <form className="command-popup standalone" onSubmit={submit}>
        <div className="command-icon">
          <MonitorUp size={20} />
        </div>
        <div className="command-stack">
          <input
            ref={inputRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask anything on your screen"
            autoFocus
          />
          <span>{status}</span>
        </div>
        <button disabled={isRunning || question.trim().length === 0}>
          {isRunning ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
        </button>
        <button type="button" className="icon-close" aria-label="Close" onClick={() => getCurrentWindow().hide()}>
          <X size={17} />
        </button>
      </form>
    </main>
  );
}
