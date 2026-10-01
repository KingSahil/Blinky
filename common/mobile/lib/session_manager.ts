import AsyncStorage from '@react-native-async-storage/async-storage';
import { Message } from '../types';

export interface BlinkyChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  mode: 'general' | 'grounded';
  linkedNotebookId?: string;
  messages: Message[];
}

const SESSIONS_INDEX_KEY = '@blinky_mobile_chat_sessions_v1';
const ACTIVE_SESSION_ID_KEY = '@blinky_mobile_active_session_id';

const DEFAULT_WELCOME_MESSAGE: Message = {
  id: 'welcome',
  sender: 'blinky',
  text: 'Hello! I am Blinky. Ask me to do anything on your PC, or attach documents to research.',
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
};

/**
 * Creates an intelligent title for a chat thread based on the user's first prompt.
 */
export function generateSessionTitle(prompt: string): string {
  if (!prompt || !prompt.trim()) return 'New Conversation';
  const clean = prompt.trim().replace(/^[\/#!?]+/, '').trim();
  const words = clean.split(/\s+/);
  if (words.length <= 5) {
    return clean.charAt(0).toUpperCase() + clean.slice(1);
  }
  return words.slice(0, 5).join(' ') + '...';
}

/**
 * Loads all saved sessions, sorted newest first.
 */
export async function listSessions(): Promise<BlinkyChatSession[]> {
  try {
    const raw = await AsyncStorage.getItem(SESSIONS_INDEX_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch (err) {
    console.warn('[SessionManager] Error listing sessions:', err);
    return [];
  }
}

/**
 * Retrieves the currently active session, or initializes a default one if none exists.
 */
export async function getActiveSession(): Promise<BlinkyChatSession> {
  try {
    const sessions = await listSessions();
    const activeId = await AsyncStorage.getItem(ACTIVE_SESSION_ID_KEY);

    if (activeId) {
      const match = sessions.find((s) => s.id === activeId);
      if (match) return match;
    }

    if (sessions.length > 0) {
      await AsyncStorage.setItem(ACTIVE_SESSION_ID_KEY, sessions[0].id);
      return sessions[0];
    }

    // No sessions exist; create the initial default session
    return await createNewSession('general', 'Welcome Session');
  } catch (err) {
    console.warn('[SessionManager] Error getting active session:', err);
    return {
      id: `session_${Date.now()}`,
      title: 'Current Session',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      mode: 'general',
      messages: [DEFAULT_WELCOME_MESSAGE],
    };
  }
}

/**
 * Saves or updates a session in persistent storage.
 */
export async function saveSession(session: BlinkyChatSession): Promise<void> {
  try {
    const sessions = await listSessions();
    const existingIndex = sessions.findIndex((s) => s.id === session.id);
    const updated = { ...session, updatedAt: Date.now() };

    if (existingIndex >= 0) {
      sessions[existingIndex] = updated;
    } else {
      sessions.unshift(updated);
    }

    await AsyncStorage.setItem(SESSIONS_INDEX_KEY, JSON.stringify(sessions));
    await AsyncStorage.setItem(ACTIVE_SESSION_ID_KEY, updated.id);
  } catch (err) {
    console.warn('[SessionManager] Error saving session:', err);
  }
}

/**
 * Creates a brand new chat session and sets it as active.
 */
export async function createNewSession(
  mode: 'general' | 'grounded' = 'general',
  title?: string
): Promise<BlinkyChatSession> {
  const newId = `session_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  const newSession: BlinkyChatSession = {
    id: newId,
    title: title || 'New Chat',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    mode,
    messages: [
      {
        ...DEFAULT_WELCOME_MESSAGE,
        id: `welcome_${Date.now()}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ],
  };

  try {
    const sessions = await listSessions();
    sessions.unshift(newSession);
    await AsyncStorage.setItem(SESSIONS_INDEX_KEY, JSON.stringify(sessions));
    await AsyncStorage.setItem(ACTIVE_SESSION_ID_KEY, newId);
  } catch (err) {
    console.warn('[SessionManager] Error creating new session:', err);
  }

  return newSession;
}

/**
 * Switches the active session to the given session ID.
 */
export async function switchSession(sessionId: string): Promise<BlinkyChatSession | null> {
  try {
    const sessions = await listSessions();
    const match = sessions.find((s) => s.id === sessionId);
    if (match) {
      await AsyncStorage.setItem(ACTIVE_SESSION_ID_KEY, sessionId);
      return match;
    }
  } catch (err) {
    console.warn('[SessionManager] Error switching session:', err);
  }
  return null;
}

/**
 * Deletes a session by ID. If it was active, switches to the next available session or creates a new one.
 */
export async function deleteSession(sessionId: string): Promise<BlinkyChatSession> {
  try {
    let sessions = await listSessions();
    sessions = sessions.filter((s) => s.id !== sessionId);
    await AsyncStorage.setItem(SESSIONS_INDEX_KEY, JSON.stringify(sessions));

    const activeId = await AsyncStorage.getItem(ACTIVE_SESSION_ID_KEY);
    if (activeId === sessionId) {
      if (sessions.length > 0) {
        await AsyncStorage.setItem(ACTIVE_SESSION_ID_KEY, sessions[0].id);
        return sessions[0];
      }
      return await createNewSession('general', 'New Chat');
    }
    return await getActiveSession();
  } catch (err) {
    console.warn('[SessionManager] Error deleting session:', err);
    return await getActiveSession();
  }
}

/**
 * Clears all stored sessions and initializes a fresh start.
 */
export async function clearAllSessions(): Promise<BlinkyChatSession> {
  try {
    await AsyncStorage.removeItem(SESSIONS_INDEX_KEY);
    await AsyncStorage.removeItem(ACTIVE_SESSION_ID_KEY);
  } catch (err) {
    console.warn('[SessionManager] Error clearing sessions:', err);
  }
  return await createNewSession('general', 'New Chat');
}
