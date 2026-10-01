import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { runTutor } from './lib/tauri';

export interface Source {
  id: string;
  source_name: string;
  file_type: string;
  word_count: number;
  active: boolean;
}

export interface Notebook {
  id: string;
  title: string;
  description: string;
  sources: Source[];
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: string;
}

interface NotebookViewProps {
  onClose: () => void;
  isStandalone?: boolean;
}

async function callNotebookRpc(action: string, params: Record<string, any>): Promise<any> {
  const payload = `[NOTEBOOK_RPC:${action}] ${JSON.stringify(params)}`;
  const res = await runTutor(payload);
  const parsed = typeof res === 'string' ? JSON.parse(res) : res;
  if (parsed.summary) {
    try {
      return JSON.parse(parsed.summary);
    } catch {
      return parsed.summary;
    }
  }
  return parsed;
}

export const NotebookView: React.FC<NotebookViewProps> = ({ onClose, isStandalone = false }) => {
  const [notebooks, setNotebooks] = useState<Notebook[]>([
    {
      id: 'default',
      title: 'Default Knowledge Hub',
      description: 'Personal research notes and uploaded documents',
      sources: [],
    },
  ]);
  const [activeNotebookId, setActiveNotebookId] = useState<string>('default');
  const [useVectorSearch, setUseVectorSearch] = useState<boolean>(true);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm1',
      sender: 'ai',
      text: 'Welcome to your **Blinky Knowledge Hub**! 📚\n\nUpload your PDFs, Markdown files, or notes on the left to ground the AI. When active, every answer is synthesized with verifiable inline citations.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const activeNotebook = notebooks.find((n) => n.id === activeNotebookId) || notebooks[0];

  // Load notebooks and persisted sources from backend on mount
  useEffect(() => {
    async function initNotebook() {
      try {
        const listRes = await callNotebookRpc('notebook_list', {});
        if (listRes && listRes.success && listRes.notebooks && listRes.notebooks.length > 0) {
          const nbs = listRes.notebooks as Notebook[];
          // Prioritize notebook that already has sources
          const primary = nbs.find((n) => n.sources && n.sources.length > 0) || nbs[0];
          setNotebooks(nbs);
          setActiveNotebookId(primary.id);
        } else {
          const createRes = await callNotebookRpc('notebook_create', {
            title: 'Default Knowledge Hub',
            description: 'Personal research notes and uploaded documents',
          });
          if (createRes && createRes.notebook) {
            setNotebooks([createRes.notebook]);
            setActiveNotebookId(createRes.notebook.id);
          }
        }
      } catch (err) {
        console.error('Failed to load notebook store:', err);
      }
    }
    void initNotebook();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || queryInput).trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: `u_${Date.now()}`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setQueryInput('');
    setLoading(true);

    try {
      const queryPayload = `[NOTEBOOK:${activeNotebook.id}] ${text}`;
      const res = await runTutor(queryPayload, undefined, undefined, undefined, false, false);
      const parsed = typeof res === 'string' ? JSON.parse(res) : res;
      const aiResponse = parsed.summary || parsed.message || 'No grounded response generated.';

      const aiMsg: ChatMessage = {
        id: `ai_${Date.now()}`,
        sender: 'ai',
        text: aiResponse,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'ai',
        text: `Error querying notebook: ${err?.message || 'Daemon unreachable'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const uploadFile = async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase() || 'txt';
    const reader = new FileReader();

    return new Promise<void>((resolve, reject) => {
      reader.onload = async () => {
        try {
          const content = reader.result as string;
          const res = await callNotebookRpc('notebook_add_source', {
            notebook_id: activeNotebook.id,
            source_name: file.name,
            content,
            file_type: ext,
          });

          if (res && res.success && res.source) {
            // Re-fetch all notebooks to keep source count & word counts exact
            const listRes = await callNotebookRpc('notebook_list', {});
            if (listRes && listRes.success && listRes.notebooks) {
              setNotebooks(listRes.notebooks);
            }
          }
          resolve();
        } catch (err) {
          console.error(`Failed uploading ${file.name}:`, err);
          reject(err);
        }
      };
      reader.onerror = (err) => reject(err);

      if (ext === 'pdf') {
        reader.readAsDataURL(file); // Encode binary PDF safely as Base64 Data URL
      } else {
        reader.readAsText(file);
      }
    });
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadFile(file);
      }
    } finally {
      setUploading(false);
    }
  };

  const toggleSourceActive = async (sourceId: string, currentActive: boolean) => {
    const nextActive = !currentActive;
    setNotebooks((prev) =>
      prev.map((nb) =>
        nb.id === activeNotebookId
          ? {
              ...nb,
              sources: nb.sources.map((s) => (s.id === sourceId ? { ...s, active: nextActive } : s)),
            }
          : nb
      )
    );

    try {
      await callNotebookRpc('notebook_toggle_source', {
        notebook_id: activeNotebookId,
        source_id: sourceId,
        active: nextActive,
      });
    } catch (err) {
      console.error('Failed toggling source:', err);
    }
  };

  const handleArtifactGenerate = (artifactType: string) => {
    let prompt = '';
    switch (artifactType) {
      case 'summary':
        prompt = 'Generate a high-level Executive Summary of all active sources in this notebook.';
        break;
      case 'faq':
        prompt = 'Generate a list of Frequently Asked Questions (FAQs) based on these notebook sources.';
        break;
      case 'study':
        prompt = 'Create a structured Study Guide with key takeaways and definitions from these sources.';
        break;
      case 'action':
        prompt = 'Extract a step-by-step Action Checklist of tasks mentioned across these notebook sources.';
        break;
    }
    if (prompt) handleSendMessage(prompt);
  };

  return (
    <div className={`notebook-overlay ${isStandalone ? 'notebook-standalone' : ''}`}>
      <div className="notebook-container">
        {/* HEADER */}
        <div className="notebook-header">
          <div className="notebook-title-area">
            <span className="notebook-badge">OKF Notebook</span>
            <h2>{activeNotebook.title}</h2>
            <button
              style={{
                marginLeft: '8px',
                padding: '4px 10px',
                fontSize: '11px',
                borderRadius: '20px',
                border: '1px solid ' + (useVectorSearch ? 'rgba(139, 92, 246, 0.4)' : 'rgba(255, 255, 255, 0.12)'),
                background: useVectorSearch ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                color: useVectorSearch ? '#c4b5fd' : '#94a3b8',
                cursor: 'pointer',
                fontWeight: 600,
                transition: 'all 0.2s ease',
              }}
              onClick={() => setUseVectorSearch(!useVectorSearch)}
              title="Toggle between Dense Vector RAG and Full Context OKF"
            >
              {useVectorSearch ? '⚡ Dense Vector RAG' : '📄 Full Context OKF'}
            </button>
          </div>
          <button className="notebook-close-btn" onClick={onClose} title="Close Workspace">
            ✕
          </button>
        </div>

        {/* 3-COLUMN WORKSPACE GRID */}
        <div className="notebook-grid">
          {/* LEFT COLUMN: SOURCES */}
          <div className="notebook-col notebook-sources-col">
            <div className="col-header">
              <h3>Sources ({activeNotebook.sources.length})</h3>
              <label className={`upload-btn ${uploading ? 'uploading' : ''}`}>
                {uploading ? 'Ingesting...' : '+ Add Source'}
                <input
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md,.json"
                  onChange={handleFileUpload}
                  style={{ display: 'none' }}
                  disabled={uploading}
                />
              </label>
            </div>

            <div
              className={`sources-dropzone ${dragOver ? 'dragover' : ''} ${uploading ? 'uploading' : ''}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={async (e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                  setUploading(true);
                  try {
                    for (const file of Array.from(e.dataTransfer.files)) {
                      await uploadFile(file);
                    }
                  } finally {
                    setUploading(false);
                  }
                }
              }}
            >
              <p>{uploading ? 'Parsing and vector-indexing files...' : 'Drag & drop PDFs, Markdown, or text documents here'}</p>
            </div>

            <div className="sources-list">
              {activeNotebook.sources.length === 0 && !uploading && (
                <div style={{ padding: '24px 12px', textAlign: 'center', color: '#64748b', fontSize: '12px' }}>
                  No sources added yet. Drop PDFs or notes above to begin.
                </div>
              )}
              {activeNotebook.sources.map((src) => (
                <div key={src.id} className={`source-card ${src.active ? 'active' : 'inactive'}`}>
                  <input
                    type="checkbox"
                    checked={src.active}
                    onChange={() => toggleSourceActive(src.id, src.active)}
                    className="source-checkbox"
                    title={src.active ? 'Disable from grounded context' : 'Enable in grounded context'}
                  />
                  <div className="source-info">
                    <span className="source-name" title={src.source_name}>
                      {src.source_name}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '3px' }}>
                      <span className={`source-badge-type ${src.file_type.toLowerCase()}`}>
                        {src.file_type.toUpperCase()}
                      </span>
                      <span className="source-meta">
                        {src.word_count.toLocaleString()} words
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* CENTER COLUMN: GROUNDED CHAT STREAM */}
          <div className="notebook-col notebook-chat-col">
            <div className="chat-stream">
              {messages.map((msg) => (
                <div key={msg.id} className={`message-bubble ${msg.sender}`}>
                  <div className="bubble-header">
                    <span className="sender-name">{msg.sender === 'user' ? 'You' : 'Blinky Notebook AI'}</span>
                    <span className="timestamp">{msg.timestamp}</span>
                  </div>
                  <div className="bubble-text">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="message-bubble ai loading">
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                  <span style={{ fontSize: '12px', color: '#94a3b8', marginLeft: '8px' }}>
                    {useVectorSearch ? 'Searching Vector Database & generating grounded response...' : 'Synthesizing grounded answer across active sources...'}
                  </span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="notebook-input-area">
              <input
                type="text"
                className="notebook-input"
                placeholder={
                  activeNotebook.sources.length === 0
                    ? 'Add a source document first to ask grounded questions...'
                    : useVectorSearch
                    ? 'Query notebook using Dense Vector Search...'
                    : 'Ask a grounded question across active sources...'
                }
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
              />
              <button className="send-btn" onClick={() => handleSendMessage()} disabled={loading}>
                Send
              </button>
            </div>
          </div>

          {/* RIGHT COLUMN: STUDIO ARTIFACTS */}
          <div className="notebook-col notebook-artifacts-col">
            <div className="col-header">
              <h3>Studio Artifacts</h3>
            </div>
            <p className="artifacts-desc">One-click generate structured knowledge artifacts from your active sources:</p>

            <div className="artifacts-buttons">
              <button
                className="artifact-btn"
                onClick={() => handleArtifactGenerate('summary')}
                disabled={activeNotebook.sources.length === 0 || loading}
              >
                <span className="btn-icon">📋</span>
                <div className="btn-text">
                  <strong>Executive Summary</strong>
                  <small>High-level key points overview</small>
                </div>
              </button>

              <button
                className="artifact-btn"
                onClick={() => handleArtifactGenerate('faq')}
                disabled={activeNotebook.sources.length === 0 || loading}
              >
                <span className="btn-icon">❓</span>
                <div className="btn-text">
                  <strong>FAQ Generator</strong>
                  <small>Question & Answer study guide</small>
                </div>
              </button>

              <button
                className="artifact-btn"
                onClick={() => handleArtifactGenerate('study')}
                disabled={activeNotebook.sources.length === 0 || loading}
              >
                <span className="btn-icon">📚</span>
                <div className="btn-text">
                  <strong>Study Guide</strong>
                  <small>Definitions & core concepts</small>
                </div>
              </button>

              <button
                className="artifact-btn"
                onClick={() => handleArtifactGenerate('action')}
                disabled={activeNotebook.sources.length === 0 || loading}
              >
                <span className="btn-icon">✅</span>
                <div className="btn-text">
                  <strong>Action Checklist</strong>
                  <small>Extracted step-by-step tasks</small>
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
