import React, { useState, useEffect, useRef } from 'react';
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
}

export const NotebookView: React.FC<NotebookViewProps> = ({ onClose }) => {
  const [notebooks, setNotebooks] = useState<Notebook[]>([
    {
      id: 'default',
      title: 'Default Knowledge Hub',
      description: 'Personal research notes and uploaded documents',
      sources: [
        { id: 's1', source_name: 'Blinky_Architecture.md', file_type: 'md', word_count: 1240, active: true },
        { id: 's2', source_name: 'OKF_Guide.pdf', file_type: 'pdf', word_count: 850, active: true },
      ],
    },
  ]);
  const [activeNotebookId, setActiveNotebookId] = useState<string>('default');
  const [useVectorSearch, setUseVectorSearch] = useState<boolean>(true);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm1',
      sender: 'ai',
      text: 'Welcome to your Blinky Notebook Hub! Upload PDFs, notes, or documents on the left. Toggle between Dense Vector RAG and Full Context OKF mode.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const activeNotebook = notebooks.find((n) => n.id === activeNotebookId) || notebooks[0];

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
      const payload = {
        question: `[NOTEBOOK:${activeNotebook.id}] ${text}`,
        agent_mode: false,
        use_vector_search: useVectorSearch,
      };
      const res = await runTutor(JSON.stringify(payload));
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

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = (evt) => {
        const content = evt.target?.result as string;
        const ext = file.name.split('.').pop()?.toLowerCase() || 'txt';
        const newSource: Source = {
          id: `src_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
          source_name: file.name,
          file_type: ext,
          word_count: Math.round(content.length / 5),
          active: true,
        };

        setNotebooks((prev) =>
          prev.map((nb) =>
            nb.id === activeNotebookId
              ? { ...nb, sources: [...nb.sources.filter((s) => s.source_name !== file.name), newSource] }
              : nb
          )
        );
      };
      reader.readAsText(file);
    });
  };

  const toggleSourceActive = (sourceId: string) => {
    setNotebooks((prev) =>
      prev.map((nb) =>
        nb.id === activeNotebookId
          ? {
              ...nb,
              sources: nb.sources.map((s) => (s.id === sourceId ? { ...s, active: !s.active } : s)),
            }
          : nb
      )
    );
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
    <div className="notebook-overlay">
      <div className="notebook-container">
        {/* HEADER */}
        <div className="notebook-header">
          <div className="notebook-title-area">
            <span className="notebook-badge">OKF Notebook</span>
            <h2>{activeNotebook.title}</h2>
            <button
              style={{
                marginLeft: '12px',
                padding: '4px 10px',
                fontSize: '12px',
                borderRadius: '6px',
                border: 'none',
                background: useVectorSearch ? '#8b5cf6' : '#334155',
                color: '#fff',
                cursor: 'pointer',
                fontWeight: 600,
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
              <label className="upload-btn">
                + Add Source
                <input type="file" multiple accept=".pdf,.txt,.md,.json" onChange={handleFileUpload} style={{ display: 'none' }} />
              </label>
            </div>

            <div
              className={`sources-dropzone ${dragOver ? 'dragover' : ''}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                  const inputEvt = { target: { files: e.dataTransfer.files } } as any;
                  handleFileUpload(inputEvt);
                }
              }}
            >
              <p>Drag & drop PDFs, Markdown, or text documents here</p>
            </div>

            <div className="sources-list">
              {activeNotebook.sources.map((src) => (
                <div key={src.id} className={`source-card ${src.active ? 'active' : 'inactive'}`}>
                  <input
                    type="checkbox"
                    checked={src.active}
                    onChange={() => toggleSourceActive(src.id)}
                    className="source-checkbox"
                  />
                  <div className="source-info">
                    <span className="source-name">{src.source_name}</span>
                    <span className="source-meta">
                      {src.file_type.toUpperCase()} • {src.word_count} words
                    </span>
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
                  <div className="bubble-text">{msg.text}</div>
                </div>
              ))}
              {loading && (
                <div className="message-bubble ai loading">
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                  <span style={{ fontSize: '12px', color: '#94a3b8', marginLeft: '8px' }}>
                    {useVectorSearch ? 'Searching Vector Database & generating response...' : 'Reading active notebook context...'}
                  </span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="notebook-input-area">
              <input
                type="text"
                className="notebook-input"
                placeholder={useVectorSearch ? 'Query notebook using Dense Vector Search...' : 'Ask a grounded question across active sources...'}
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
              <button className="artifact-btn" onClick={() => handleArtifactGenerate('summary')}>
                <span className="btn-icon">📋</span>
                <div className="btn-text">
                  <strong>Executive Summary</strong>
                  <small>High-level key points overview</small>
                </div>
              </button>

              <button className="artifact-btn" onClick={() => handleArtifactGenerate('faq')}>
                <span className="btn-icon">❓</span>
                <div className="btn-text">
                  <strong>FAQ Generator</strong>
                  <small>Question & Answer study guide</small>
                </div>
              </button>

              <button className="artifact-btn" onClick={() => handleArtifactGenerate('study')}>
                <span className="btn-icon">📚</span>
                <div className="btn-text">
                  <strong>Study Guide</strong>
                  <small>Definitions & core concepts</small>
                </div>
              </button>

              <button className="artifact-btn" onClick={() => handleArtifactGenerate('action')}>
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
