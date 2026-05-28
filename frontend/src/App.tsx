import {
  ArrowUp,
  Bookmark,
  CheckCircle2,
  Clock,
  Keyboard,
  MessageSquareText,
  Settings,
  Sparkles,
  UserCircle2,
  Loader2,
} from 'lucide-react';
import { useState, FormEvent } from 'react';
import { hideOverlay, showCommandBar, showOverlay, runTutor } from './lib/tauri';

export function App() {
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  
  const [question, setQuestion] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  
  const [activeTab, setActiveTab] = useState<'chats' | 'history' | 'saved'>('chats');
  const [shortcutKey, setShortcutKey] = useState('Enter');

  async function toggleOverlay() {
    const next = !overlayEnabled;
    setOverlayEnabled(next);
    if (next) {
      await showOverlay();
    } else {
      await hideOverlay();
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isRunning) return;

    setIsRunning(true);
    setStatus('Reading the screen...');
    try {
      const result = await runTutor(trimmed);
      await showOverlay();
      setStatus(result.summary);
      setQuestion('');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient-grid" aria-hidden="true" />
      <header className="titlebar" data-tauri-drag-region>
        <div className="brand" data-tauri-drag-region>
          <div className="brand-mark">
            <Sparkles size={18} />
          </div>
          <div>
            <h1>Clicky</h1>
            <span>Configuration and status</span>
          </div>
        </div>
        <div className="titlebar-actions">
          <div className="ready-pill">
            <CheckCircle2 size={15} />
            Ready
          </div>
        </div>
      </header>

      <section className={`app-workspace ${!settingsOpen ? 'settings-closed' : ''}`}>
        <aside className="nav-rail">
          <div className="nav-section">
            <button 
              className={`nav-item ${activeTab === 'chats' ? 'active' : ''}`}
              onClick={() => setActiveTab('chats')}
            >
              <MessageSquareText size={16} />
              Chats
            </button>
            <button 
              className={`nav-item ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              <Clock size={16} />
              History
            </button>
            <button 
              className={`nav-item ${activeTab === 'saved' ? 'active' : ''}`}
              onClick={() => setActiveTab('saved')}
            >
              <Bookmark size={16} />
              Saved
            </button>
          </div>

          <div className="nav-footer">
            <div className="user-card">
              <div className="user-avatar">
                <UserCircle2 size={20} />
              </div>
              <div>
                <strong>Arjun</strong>
                <span>Pro Plan</span>
              </div>
            </div>
            <button 
              className={`nav-item settings-item ${settingsOpen ? 'active' : ''}`}
              onClick={() => setSettingsOpen(!settingsOpen)}
            >
              <Settings size={16} />
              Settings
            </button>
          </div>
        </aside>

        <section className="center-panel">
          {activeTab === 'chats' && (
            <>
              <div className="hero-card">
                <h2>How can I help you today?</h2>
                <p>Ask anything. Get instant answers.</p>
              </div>

              {status && <div className="status-tile"><strong>{status}</strong></div>}

              <form className="composer hero-composer" onSubmit={submit}>
                <input 
                  placeholder="Ask anything..." 
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                />
                <button className="send-button" aria-label="Send message" type="submit" disabled={isRunning || !question.trim()}>
                  {isRunning ? <Loader2 size={16} className="spin" /> : <ArrowUp size={16} />}
                </button>
              </form>

              <div className="hint-row">
                <Keyboard size={14} />
                <span>Press Ctrl + Shift + {shortcutKey} to open full window</span>
              </div>
            </>
          )}

          {activeTab === 'history' && (
            <div className="hero-card">
              <h2>History</h2>
              <p>Your previous conversations will appear here.</p>
            </div>
          )}

          {activeTab === 'saved' && (
            <div className="hero-card">
              <h2>Saved</h2>
              <p>Your saved snippets and chats will appear here.</p>
            </div>
          )}
        </section>

        <aside className="settings-panel">
          <div className="settings-header">
            <div>
              <h2>Settings</h2>
              <p>Change LLM</p>
            </div>
            <div className="ready-pill">
              <CheckCircle2 size={15} />
              Ready
            </div>
          </div>

          <div className="settings-section">
            <h3>Change LLM</h3>
            <div className="provider-list">
              <button className="provider-option active">
                <span>Groq</span>
                <span className="provider-chip">Active</span>
              </button>
              <button className="provider-option">
                <span>Ollama</span>
              </button>
            </div>
          </div>

          <div className="settings-section">
            <h3>Overlay</h3>
            <button className="toggle-row" onClick={toggleOverlay} aria-pressed={overlayEnabled}>
              <span>Enable overlay</span>
              <span className={`toggle ${overlayEnabled ? 'on' : ''}`} />
            </button>
          </div>

          <div className="settings-section">
            <h3>Global shortcut</h3>
            <div className="shortcut-row">
              <span>Ctrl</span>
              <span>Shift</span>
              <select 
                className="shortcut-select"
                value={shortcutKey}
                onChange={(e) => setShortcutKey(e.target.value)}
              >
                <option value="Enter">Enter</option>
                <option value="Space">Space</option>
                <option value="P">P</option>
                <option value="K">K</option>
              </select>
            </div>
          </div>

          <div className="settings-section">
            <h3>Open chat bar</h3>
            <button className="primary-action" onClick={() => void showCommandBar()}>
              <MessageSquareText size={18} />
              Open chat bar
            </button>
          </div>

          <div className="settings-section info">
            <div className="info-row">
              <span>Theme</span>
              <strong>Ember</strong>
            </div>
            <div className="info-row">
              <span>About Clicky</span>
              <strong>v1.0.0</strong>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
