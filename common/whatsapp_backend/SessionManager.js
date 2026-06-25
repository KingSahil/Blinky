// SessionManager.js — manages multiple per-user WaUserSession instances
import { readFile, writeFile, mkdir } from 'fs/promises';
import { join } from 'path';
import { WaUserSession } from './WaUserSession.js';

const SESSIONS_FILE = join(process.cwd(), 'data', 'sessions.json');

// In-memory map of sessionId → WaUserSession
const sessions = new Map();

let _io = null;

async function loadSessionRegistry() {
    try {
        const raw = await readFile(SESSIONS_FILE, 'utf-8');
        return JSON.parse(raw);
    } catch {
        return {};
    }
}

async function saveSessionRegistry(registry) {
    await mkdir(join(process.cwd(), 'data'), { recursive: true });
    await writeFile(SESSIONS_FILE, JSON.stringify(registry, null, 2), 'utf-8');
}

/**
 * Called once at server startup — restores any previously registered sessions.
 */
export async function initSessionManager(io) {
    _io = io;
    const registry = await loadSessionRegistry();
    for (const [sessionId] of Object.entries(registry)) {
        console.log(`[SessionManager] Restoring session ${sessionId.slice(0, 8)}...`);
        const session = new WaUserSession(sessionId, _io);
        sessions.set(sessionId, session);
        await session.start();
    }
    console.log(`[SessionManager] ${sessions.size} session(s) restored.`);
}

/**
 * Returns an existing session, or creates + starts a new one.
 */
export async function getOrCreateSession(sessionId) {
    if (sessions.has(sessionId)) {
        return { session: sessions.get(sessionId), isNew: false };
    }

    const session = new WaUserSession(sessionId, _io);
    sessions.set(sessionId, session);

    const registry = await loadSessionRegistry();
    registry[sessionId] = { createdAt: new Date().toISOString() };
    await saveSessionRegistry(registry);

    await session.start();
    return { session, isNew: true };
}

/**
 * Returns an existing session or null.
 */
export function getSession(sessionId) {
    return sessions.get(sessionId) || null;
}
