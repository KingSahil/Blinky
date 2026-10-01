export interface PcChatMessage {
  role: 'user' | 'assistant';
  text: string;
  timestamp: number;
  steps?: string[];
}

export interface PcChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: PcChatMessage[];
}

const PC_SESSIONS_KEY = 'blinky_pc_chat_sessions_v1';
const PC_ACTIVE_SESSION_ID_KEY = 'blinky_pc_active_session_id';

export function generatePcSessionTitle(prompt: string): string {
  if (!prompt || !prompt.trim()) return 'New Conversation';
  const clean = prompt.trim().replace(/^[\/#!?]+/, '').trim();
  const words = clean.split(/\s+/);
  if (words.length <= 5) {
    return clean.charAt(0).toUpperCase() + clean.slice(1);
  }
  return words.slice(0, 5).join(' ') + '...';
}

function isValidChatMessage(m: unknown): m is PcChatMessage {
  if (!m || typeof m !== 'object') return false;
  const msg = m as Record<string, unknown>;
  if (msg.role !== 'user' && msg.role !== 'assistant') return false;
  if (typeof msg.text !== 'string') return false;
  if (typeof msg.timestamp !== 'number') return false;
  if (msg.steps !== undefined && !Array.isArray(msg.steps)) return false;
  return true;
}

export function listPcChatSessions(): PcChatSession[] {
  try {
    const raw = localStorage.getItem(PC_SESSIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    const validSessions: PcChatSession[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const s = item as Record<string, unknown>;
      if (typeof s.id !== 'string' || !s.id.trim()) continue;
      if (!Array.isArray(s.messages)) continue;

      const validMessages = s.messages.filter(isValidChatMessage);
      validSessions.push({
        id: s.id,
        title: typeof s.title === 'string' ? s.title : 'New Conversation',
        createdAt: typeof s.createdAt === 'number' ? s.createdAt : Date.now(),
        updatedAt: typeof s.updatedAt === 'number' ? s.updatedAt : (typeof s.createdAt === 'number' ? s.createdAt : Date.now()),
        messages: validMessages,
      });
    }

    return validSessions.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch (err) {
    console.warn('[sessionStorage] Failed to read PC sessions:', err);
    return [];
  }
}

export function getActivePcSession(): PcChatSession {
  try {
    const sessions = listPcChatSessions();
    const activeId = localStorage.getItem(PC_ACTIVE_SESSION_ID_KEY);

    if (activeId) {
      const match = sessions.find((s) => s.id === activeId);
      if (match) return match;
    }

    if (sessions.length > 0) {
      localStorage.setItem(PC_ACTIVE_SESSION_ID_KEY, sessions[0].id);
      return sessions[0];
    }

    return createPcChatSession('Initial Session');
  } catch (err) {
    console.warn('[sessionStorage] Failed to get active session:', err);
    return {
      id: `pc_sess_${Date.now()}`,
      title: 'Current Session',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    };
  }
}

export function savePcChatSession(session: PcChatSession): void {
  try {
    const sessions = listPcChatSessions();
    const existingIndex = sessions.findIndex((s) => s.id === session.id);
    const updated = { ...session, updatedAt: Date.now() };

    if (existingIndex >= 0) {
      sessions[existingIndex] = updated;
    } else {
      sessions.unshift(updated);
    }

    localStorage.setItem(PC_SESSIONS_KEY, JSON.stringify(sessions));
    localStorage.setItem(PC_ACTIVE_SESSION_ID_KEY, updated.id);
  } catch (err) {
    console.warn('[sessionStorage] Failed to save session:', err);
  }
}

export function createPcChatSession(title?: string): PcChatSession {
  const newId = `pc_sess_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
  const newSession: PcChatSession = {
    id: newId,
    title: title || 'New Conversation',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
  };

  try {
    const sessions = listPcChatSessions();
    sessions.unshift(newSession);
    localStorage.setItem(PC_SESSIONS_KEY, JSON.stringify(sessions));
    localStorage.setItem(PC_ACTIVE_SESSION_ID_KEY, newId);
  } catch (err) {
    console.warn('[sessionStorage] Failed to create session:', err);
  }

  return newSession;
}

export function switchPcChatSession(sessionId: string): PcChatSession | null {
  try {
    const sessions = listPcChatSessions();
    const match = sessions.find((s) => s.id === sessionId);
    if (match) {
      localStorage.setItem(PC_ACTIVE_SESSION_ID_KEY, sessionId);
      return match;
    }
  } catch (err) {
    console.warn('[sessionStorage] Failed to switch session:', err);
  }
  return null;
}

export function deletePcChatSession(sessionId: string): PcChatSession {
  try {
    let sessions = listPcChatSessions();
    sessions = sessions.filter((s) => s.id !== sessionId);
    localStorage.setItem(PC_SESSIONS_KEY, JSON.stringify(sessions));

    const activeId = localStorage.getItem(PC_ACTIVE_SESSION_ID_KEY);
    if (activeId === sessionId) {
      if (sessions.length > 0) {
        localStorage.setItem(PC_ACTIVE_SESSION_ID_KEY, sessions[0].id);
        return sessions[0];
      }
      return createPcChatSession('New Conversation');
    }
    return getActivePcSession();
  } catch (err) {
    console.warn('[sessionStorage] Failed to delete session:', err);
    return getActivePcSession();
  }
}

export function clearAllPcChatSessions(): PcChatSession {
  try {
    localStorage.removeItem(PC_SESSIONS_KEY);
    localStorage.removeItem(PC_ACTIVE_SESSION_ID_KEY);
  } catch (err) {
    console.warn('[sessionStorage] Failed to clear sessions:', err);
  }
  return createPcChatSession('New Conversation');
}
