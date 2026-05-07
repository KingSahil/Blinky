import { listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import {
  Bot,
  CheckCircle2,
  Eye,
  EyeOff,
  Keyboard,
  Loader2,
  Maximize2,
  MessageSquareText,
  Minus,
  MonitorUp,
  Play,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { hideOverlay, runTutor, showOverlay } from './lib/tauri';
import type { ChatMessage, TutorResult } from './lib/types';

const starterMessages: ChatMessage[] = [
  {
    id: 'welcome',
    role: 'clicky',
    content:
      'Ask me about the app currently on your screen. I will read visible text and show only steps I can point to.',
  },
];

export function App() {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>(starterMessages);
  const [isRunning, setIsRunning] = useState(false);
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [commandOpen, setCommandOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const latestResult = useMemo(
    () => [...messages].reverse().find((message) => message.result)?.result,
    [messages],
  );

  useEffect(() => {
    const unlisten = listen('clicky://open-command', () => {
      setCommandOpen(true);
      window.setTimeout(() => inputRef.current?.focus(), 80);
    });

    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  async function submitAsk(event?: FormEvent) {
    event?.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isRunning) return;

    setQuestion('');
    setError(null);
    setCommandOpen(false);
    setIsRunning(true);

    const studentMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'student',
      content: trimmed,
    };
    setMessages((current) => [...current, studentMessage]);

    try {
      const result = await runTutor(trimmed);
      if (overlayEnabled) {
        await showOverlay();
      }
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'clicky',
          content: result.summary,
          result,
        },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'clicky',
          content: `I could not complete that capture yet. ${message}`,
        },
      ]);
    } finally {
      setIsRunning(false);
    }
  }

  async function toggleOverlay() {
    const next = !overlayEnabled;
    setOverlayEnabled(next);
    if (next) {
      await showOverlay();
    } else {
      await hideOverlay();
    }
  }

  return (
    <main className="app-shell">
      <header className="titlebar" data-tauri-drag-region>
        <div className="brand" data-tauri-drag-region>
          <div className="brand-mark">
            <Sparkles size={18} />
          </div>
          <div>
            <h1>Clicky</h1>
            <span>AI tutor for the screen in front of you</span>
          </div>
        </div>
        <div className="window-actions">
          <button aria-label="Minimize" onClick={() => getCurrentWindow().minimize()}>
            <Minus size={16} />
          </button>
          <button aria-label="Maximize" onClick={() => getCurrentWindow().toggleMaximize()}>
            <Maximize2 size={15} />
          </button>
          <button aria-label="Close" onClick={() => getCurrentWindow().close()}>
            <X size={16} />
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="side-rail">
          <div className="hotkey">
            <Keyboard size={19} />
            <div>
              <span>Ctrl + Shift + Space</span>
              <small>Open command popup</small>
            </div>
          </div>

          <button className="primary-action" onClick={() => setCommandOpen(true)}>
            <MessageSquareText size={18} />
            Ask anything on your screen
          </button>

          <button className="ghost-action" onClick={toggleOverlay}>
            {overlayEnabled ? <Eye size={18} /> : <EyeOff size={18} />}
            Overlay
            <span>{overlayEnabled ? 'On' : 'Off'}</span>
          </button>

          <StatusGrid result={latestResult} isRunning={isRunning} />
        </aside>

        <section className="chat-panel">
          <div className="chat-header">
            <div>
              <h2>Screen Tutor</h2>
              <p>Visible UI only. Short, beginner-friendly steps.</p>
            </div>
            <div className="ready-pill">
              {isRunning ? <Loader2 className="spin" size={15} /> : <CheckCircle2 size={15} />}
              {isRunning ? 'Thinking' : 'Ready'}
            </div>
          </div>

          <div className="messages">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="avatar">{message.role === 'clicky' ? <Bot size={17} /> : 'You'}</div>
                <div className="bubble">
                  <p>{message.content}</p>
                  {message.result ? <Steps result={message.result} /> : null}
                </div>
              </article>
            ))}
            {isRunning ? (
              <article className="message clicky">
                <div className="avatar">
                  <Bot size={17} />
                </div>
                <div className="bubble loading-bubble">
                  <Loader2 className="spin" size={18} />
                  Capturing screen, reading UI text, and asking Gemma...
                </div>
              </article>
            ) : null}
          </div>

          {error ? <div className="error-strip">{error}</div> : null}

          <form className="composer" onSubmit={submitAsk}>
            <Search size={19} />
            <input
              ref={inputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="How do I export this?"
              disabled={isRunning}
            />
            <button disabled={isRunning || question.trim().length === 0}>
              {isRunning ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
              Run Tutor
            </button>
          </form>
        </section>

        <Preview result={latestResult} />
      </section>

      {commandOpen ? (
        <div className="command-backdrop" onClick={() => setCommandOpen(false)}>
          <form className="command-popup" onSubmit={submitAsk} onClick={(event) => event.stopPropagation()}>
            <div className="command-icon">
              <MonitorUp size={20} />
            </div>
            <input
              ref={inputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask anything on your screen"
              autoFocus
            />
            <button disabled={isRunning || question.trim().length === 0}>
              {isRunning ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            </button>
          </form>
        </div>
      ) : null}
    </main>
  );
}

function StatusGrid({ result, isRunning }: { result?: TutorResult; isRunning: boolean }) {
  const items = [
    ['Screen', isRunning ? 'Capturing' : result?.screenshot ? 'Captured' : 'Idle'],
    ['OCR', result ? `${result.ocr.count} texts` : 'Waiting'],
    ['App', result?.active_app.process || 'Unknown'],
    ['Ollama', result ? `${result.elapsed_ms} ms` : 'Local'],
  ];

  return (
    <div className="status-grid">
      {items.map(([label, value]) => (
        <div className="status-tile" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function Steps({ result }: { result: TutorResult }) {
  return (
    <ol className="steps">
      {result.steps.map((step) => (
        <li key={`${step.step}-${step.instruction}`}>
          <span>{step.step}</span>
          <div>
            <p>{step.instruction}</p>
            <small>{step.target_text || 'No visible target'}</small>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Preview({ result }: { result?: TutorResult }) {
  const matches = result?.steps
    .map((step) => step.match)
    .filter((match): match is NonNullable<typeof match> => Boolean(match))
    .slice(0, 4);

  return (
    <aside className="preview-panel">
      <div className="preview-header">
        <h2>Live Preview</h2>
        <span>{matches?.length || 0} targets</span>
      </div>
      <div className="screen-preview">
        <div className="fake-window-line" />
        <div className="fake-sidebar" />
        <div className="fake-content">
          {(matches?.length ? matches : fallbackPreviewTargets).map((match, index) => (
            <div
              className="preview-highlight"
              key={`${match.text}-${index}`}
              style={{
                left: `${12 + index * 14}%`,
                top: `${22 + index * 14}%`,
                width: `${Math.min(46, Math.max(18, match.width / 4))}%`,
              }}
            >
              {match.text}
            </div>
          ))}
        </div>
      </div>
      <div className="preview-meta">
        <span>{result?.active_app.title || 'No capture yet'}</span>
        <small>{result?.warnings?.[0] || 'Targets are highlighted after each run.'}</small>
      </div>
    </aside>
  );
}

const fallbackPreviewTargets = [
  { text: 'Extensions', x: 0, y: 0, width: 112, height: 32, confidence: 0.9 },
  { text: 'Python', x: 0, y: 0, width: 80, height: 32, confidence: 0.9 },
];
