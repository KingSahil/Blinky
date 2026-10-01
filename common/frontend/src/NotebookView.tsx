import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { runTutor } from './lib/tauri';
import { Zap, Minus, Square, X, Plus, Upload, FileText, Sparkles, Paperclip, Send, Box, ChevronRight, MessageCircleQuestion, Layers, CheckSquare, Lightbulb, Globe, Mic } from 'lucide-react';

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

  useEffect(() => {
    async function initNotebook() {
      try {
        const listRes = await callNotebookRpc('notebook_list', {});
        if (listRes && listRes.success && listRes.notebooks && listRes.notebooks.length > 0) {
          const nbs = listRes.notebooks as Notebook[];
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
        reader.readAsDataURL(file);
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
          <div className="header-left">
            <img src="/logo_text.png" alt="Blinky" className="header-logo" />
            <span className="notebook-badge-red">OKF NOTEBOOK</span>
            <span className="notebook-title-caps">DEFAULT KNOWLEDGE HUB</span>
            <button className="rag-badge" onClick={() => setUseVectorSearch(!useVectorSearch)} title="Toggle between Dense Vector RAG and Full Context OKF">
              <Zap size={12} /> {useVectorSearch ? 'Dense Vector RAG' : 'Full Context OKF'}
            </button>
          </div>
        </div>

        {/* 3-COLUMN WORKSPACE GRID */}
        <div className="notebook-grid">
          
          {/* LEFT COLUMN: SOURCES */}
          <div className="notebook-col notebook-sources-col">
            <div className="col-header-flex">
              <h3>SOURCES ({activeNotebook.sources.length})</h3>
              <label className="add-source-btn">
                <Plus size={14} /> Add Source
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
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
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
              <Upload size={24} color={uploading ? "#94a3b8" : "#FF5A00"} style={{opacity: uploading ? 0.5 : 0.8}} />
              <p>{uploading ? 'Parsing and vector-indexing files...' : 'Drag & drop PDFs, Markdown, or text documents here'}</p>
              {!uploading && <small>Supported: PDF, MD, TXT</small>}
            </div>

            <div className="sources-list">
              {activeNotebook.sources.length === 0 && !uploading && (
                <div className="empty-sources">

                  <p>No sources added yet.<br/>Drop PDFs or notes above to begin.</p>
                </div>
              )}
              {activeNotebook.sources.map((src) => (
                <div key={src.id} className={`source-card ${src.active ? 'active' : 'inactive'}`} style={{display: 'flex', gap: '12px', padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', marginBottom: '8px', border: '1px solid rgba(255,255,255,0.05)', opacity: src.active ? 1 : 0.5}}>
                  <input
                    type="checkbox"
                    checked={src.active}
                    onChange={() => toggleSourceActive(src.id, src.active)}
                    className="source-checkbox"
                    title={src.active ? 'Disable from grounded context' : 'Enable in grounded context'}
                  />
                  <div className="source-info" style={{flex: 1, minWidth: 0}}>
                    <div className="source-name" title={src.source_name} style={{fontSize: '13px', color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '4px'}}>
                      {src.source_name}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`source-badge-type`} style={{fontSize: '10px', background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', fontWeight: 600}}>
                        {src.file_type.toUpperCase()}
                      </span>
                      <span className="source-meta" style={{fontSize: '11px', color: 'rgba(255,255,255,0.5)'}}>
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
              {messages.length === 1 && messages[0].sender === 'ai' ? (
                <div className="welcome-card">
                  <div className="welcome-icon">
                    <Sparkles size={24} color="#FF5A00" />
                  </div>
                  <div className="welcome-content">
                    <div className="welcome-header">
                      <span className="ai-label">Blinky Notebook AI</span>
                      <span className="time-label">{messages[0].timestamp}</span>
                    </div>
                    <h2>Welcome to your <span className="highlight">Blinky Knowledge Hub!</span> 📚</h2>
                    <p>Upload your PDFs, Markdown files, or notes on the left to ground the AI. When active, every answer is synthesized with verifiable inline citations.</p>
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`message-bubble ${msg.sender}`} style={{maxWidth: '80%', padding: '16px', borderRadius: '16px'}}>
                    <div className="bubble-header" style={{display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '12px', color: 'rgba(255,255,255,0.5)'}}>
                      <span className="sender-name">{msg.sender === 'user' ? 'You' : 'Blinky Notebook AI'}</span>
                      <span className="timestamp">{msg.timestamp}</span>
                    </div>
                    <div className="bubble-text" style={{fontSize: '14px', lineHeight: 1.6}}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                    </div>
                  </div>
                ))
              )}
              {loading && (
                <div className="message-bubble ai loading" style={{padding: '16px'}}>
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

            <div className={`composer-wrapper ${queryInput || dragOver ? 'expanded' : ''}`}>
              <div className="composer-row">
                <button className="composer-btn-icon" title="Attach file" type="button" tabIndex={-1}>
                  <Paperclip size={20} />
                </button>

                <div className="composer-input-container">
                  <input
                    type="text"
                    className="composer-input"
                    value={queryInput}
                    onChange={(e) => setQueryInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                    placeholder=""
                  />
                  {!queryInput && (
                    <div className="composer-placeholder">
                      {(activeNotebook.sources.length === 0
                        ? 'Add a source document first to ask grounded questions...'
                        : useVectorSearch
                        ? 'Query notebook using Dense Vector Search...'
                        : 'Ask a grounded question across active sources...'
                      ).split('').map((char, i) => (
                        <span key={i} className="composer-placeholder-char" style={{animationDelay: `${i * 0.02}s`}}>
                          {char === ' ' ? '\u00A0' : char}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <button className="composer-btn-icon" title="Voice input" type="button" tabIndex={-1}>
                  <Mic size={20} />
                </button>
                <button className="composer-send" onClick={() => handleSendMessage()} disabled={loading} type="button" tabIndex={-1}>
                  <Send size={18} />
                </button>
              </div>

              <div className="composer-expanded-controls">
                <button
                  className="composer-toggle-btn active"
                  title="Think"
                  type="button"
                >
                  <Lightbulb size={16} /> Think
                </button>
                <button
                  className={`composer-toggle-btn ${useVectorSearch ? 'active' : ''}`}
                  title="Deep Search"
                  type="button"
                  onClick={() => setUseVectorSearch(!useVectorSearch)}
                >
                  <Globe size={16} /> Deep Search
                </button>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN: STUDIO ARTIFACTS */}
          <div className="notebook-col notebook-artifacts-col">
            <div className="col-header-flex">
              <h3 style={{display:'flex', alignItems:'center', gap:'8px'}}><Box size={16} /> STUDIO ARTIFACTS</h3>
            </div>
            <p className="artifacts-desc">One-click generate structured knowledge artifacts from your active sources:</p>

            <div className="artifact-cards">
              <div className="artifact-card ac-exec" onClick={() => handleArtifactGenerate('summary')}>
                <div className="ac-icon"><FileText size={18} /></div>
                <div className="ac-text">
                  <h4>Executive Summary</h4>
                  <p>High-level key points overview</p>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="artifact-card ac-faq" onClick={() => handleArtifactGenerate('faq')}>
                <div className="ac-icon"><MessageCircleQuestion size={18} /></div>
                <div className="ac-text">
                  <h4>FAQ Generator</h4>
                  <p>Question & Answer study guide</p>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="artifact-card ac-study" onClick={() => handleArtifactGenerate('study')}>
                <div className="ac-icon"><Layers size={18} /></div>
                <div className="ac-text">
                  <h4>Study Guide</h4>
                  <p>Definitions & core concepts</p>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="artifact-card ac-action" onClick={() => handleArtifactGenerate('action')}>
                <div className="ac-icon"><CheckSquare size={18} /></div>
                <div className="ac-text">
                  <h4>Action Checklist</h4>
                  <p>Extracted step-by-step tasks</p>
                </div>
                <ChevronRight size={16} />
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

