// WaUserSession.js — per-user WhatsApp client + all related logic
import pkg from 'whatsapp-web.js';
import qrcode from 'qrcode-terminal';
import Groq from 'groq-sdk';
import axios from 'axios';
import { readFile, writeFile, unlink, mkdir, appendFile, rm } from 'fs/promises';
import { join, dirname } from 'path';
import systemPrompt from './generated-prompt.cjs';

const { Client, LocalAuth } = pkg;

// ── Module-level constants (system-wide, not per-user) ────────────────────────
const WATCHDOG_INTERVAL    = 2 * 60 * 1000;
const WATCHDOG_TIMEOUT     = 30 * 1000;
const UNREAD_SYNC_INTERVAL = 30 * 1000;
const SUPPORTED_VISION_MIME_TYPES = new Set(['image/jpeg', 'image/jpg', 'image/png']);
const SHOW_TERMINAL_QR = (process.env.SHOW_TERMINAL_QR || 'false').toLowerCase() === 'true';

// ── Pure utility helpers ──────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function isRetriableAuthCleanupError(err) {
    const code = String(err?.code || '').toUpperCase();
    return code === 'EBUSY' || code === 'EPERM' || code === 'ENOTEMPTY';
}

function withTimeout(promise, ms, label = '') {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(
            () => reject(new Error(`[TIMEOUT] ${label} did not respond within ${ms} ms`)),
            ms
        );
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function sanitizeForWhatsApp(text) {
    if (!text) return '';
    return text
        .replace(/\*\*(.*?)\*\*/g, '*$1*')
        .replace(/__(.*?)__/g, '_$1_')
        .replace(/~~(.*?)~~/g, '~$1~')
        .replace(/^\s{0,3}#{1,6}\s+(.+)$/gm, '*$1*')
        .replace(/^\s*\*\s+/gm, '- ')
        .replace(/^\s*(\d+)\)\s+/gm, '$1. ')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

function trimTo(str, max = 240) {
    if (!str) return '';
    return str.length > max ? `${str.slice(0, max - 1)}...` : str;
}

// Word count tools
function getWordCount(text) {
    return String(text || '').trim().split(/\s+/).filter(Boolean).length;
}

function extractRequestedWordCount(question) {
    const q = String(question || '');
    const match = q.match(/(?:exactly|in|with|use)?\s*(\d+)\s+words?\b/i);
    if (!match) return null;
    const parsed = parseInt(match[1], 10);
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1000) return null;
    return parsed;
}

function forceWordCount(text, targetWords) {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    if (words.length === targetWords) return words.join(' ');
    if (words.length > targetWords) return words.slice(0, targetWords).join(' ');
    const padded = [...words];
    while (padded.length < targetWords) padded.push('...');
    return padded.join(' ');
}

function isTargetClosedError(err) {
    const msg = String(err?.message || '').toLowerCase();
    return msg.includes('target closed') || msg.includes('execution context was destroyed');
}

function isSummarizeCommand(text) {
    const body = String(text || '').trim().toLowerCase();
    return body.startsWith('!summarise') || body.startsWith('!summarize') || body.startsWith('!summaries') || body.startsWith('!summarze');
}

function parseSummaryTimeWindow(text) {
    const input = String(text || '').trim();
    if (!input) return null;

    const match = input.match(/^(.*?)(?:\s+)?last\s+(?:(\d+)\s+)?(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks|month|months)\s*$/i);
    if (!match) return null;

    const remaining = String(match[1] || '').trim();
    const amount = Math.max(1, parseInt(match[2] || '1', 10));
    const unitRaw = String(match[3] || '').toLowerCase();

    let unitMs = 0;
    let unitLabel = '';
    if (['minute', 'minutes', 'min', 'mins'].includes(unitRaw)) {
        unitMs = 60 * 1000;
        unitLabel = amount === 1 ? 'minute' : 'minutes';
    } else if (['hour', 'hours', 'hr', 'hrs'].includes(unitRaw)) {
        unitMs = 60 * 60 * 1000;
        unitLabel = amount === 1 ? 'hour' : 'hours';
    } else if (['day', 'days'].includes(unitRaw)) {
        unitMs = 24 * 60 * 60 * 1000;
        unitLabel = amount === 1 ? 'day' : 'days';
    } else if (['week', 'weeks'].includes(unitRaw)) {
        unitMs = 7 * 24 * 60 * 60 * 1000;
        unitLabel = amount === 1 ? 'week' : 'weeks';
    } else if (['month', 'months'].includes(unitRaw)) {
        unitMs = 30 * 24 * 60 * 60 * 1000;
        unitLabel = amount === 1 ? 'month' : 'months';
    }

    if (!unitMs) return null;
    return {
        sinceMs: Date.now() - amount * unitMs,
        label: `last ${amount} ${unitLabel}`,
        remaining,
    };
}

function messageTimestampMs(message) {
    const ts = Number(message?.timestamp || 0);
    if (!Number.isFinite(ts) || ts <= 0) return 0;
    // whatsapp-web.js timestamps are usually epoch seconds.
    return ts > 1_000_000_000_000 ? ts : ts * 1000;
}

function isNoImportantUpdatesSummary(text) {
    const normalized = String(text || '').trim().toLowerCase();
    return normalized === '- no important updates in this chat window.'
        || normalized === 'no important updates in this chat window.';
}

function isGeneralCommand(text) {
    return String(text || '').trim().toLowerCase().startsWith('!general');
}

function messageIdOf(message) {
    return message?.id?._serialized || message?.id?.id || '';
}

function normalizeName(name) {
    return String(name || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function extractPhoneFromJid(jid) {
    const raw = String(jid || '');
    const match = raw.match(/(\d{6,15})/);
    return match ? match[1] : '';
}

// ── WaUserSession class ───────────────────────────────────────────────────────
export class WaUserSession {
    constructor(sessionId, io) {
        this.sessionId = sessionId;
        this.io = io;

        // Per-user file paths
        this.settingsFile      = join(process.cwd(), 'data', 'users', sessionId, 'settings.json');
        this.summaryMemoryFile = join(process.cwd(), 'data', 'users', sessionId, 'summary-memory.json');
        this.logFile           = join(process.cwd(), 'data', 'users', sessionId, 'wa.log');

        // Per-user runtime state
        this.userSettings        = {};
        this.groq                = null;
        this.groqKey             = '';
        this.status              = 'loading';
        this.qr                  = null;
        this.client              = null;
        this.watchdogTimer       = null;
        this.unreadSyncTimer     = null;
        this.restartTimer        = null;
        this.restarting          = false;
        this.unreadSummaryBuckets = new Map();
        this.runtimeFetchCache   = new Map();
        this.memoryWriteQueue    = Promise.resolve();
        this.logWriteQueue       = Promise.resolve();
    }

    // ── Settings ──────────────────────────────────────────────────────────────
    // User-level settings override process.env defaults.
    getSetting(key, defaultVal = '') {
        const v = this.userSettings[key];
        if (v !== undefined && v !== '') return v;
        return process.env[key] || defaultVal;
    }

    getStatus() {
        return { status: this.status, qr: this.qr };
    }

    getSettingsForApi() {
        return {
            GROQ_API_KEY:          this.getSetting('GROQ_API_KEY') ? '***' : '',
            GROQ_API_KEY_SET:      Boolean(this.getSetting('GROQ_API_KEY')),
            GROQ_MODEL:            this.getSetting('GROQ_MODEL'),
            NTFY_TOPIC:            this.getSetting('NTFY_TOPIC'),
            NTFY_TOPIC_SET:        Boolean(this.getSetting('NTFY_TOPIC')),
            TUTORIAL_SEEN:         this.userSettings.TUTORIAL_SEEN === 'true',
            NTFY_TITLE:            this.getSetting('NTFY_TITLE'),
            NTFY_PRIORITY:         this.getSetting('NTFY_PRIORITY'),
            DEFAULT_MESSAGE_LIMIT: this.getSetting('DEFAULT_MESSAGE_LIMIT', '50'),
        };
    }

    async loadSettings() {
        try {
            const raw = await readFile(this.settingsFile, 'utf-8');
            this.userSettings = JSON.parse(raw);
        } catch {
            this.userSettings = {};
        }
    }

    async saveSettings(updates) {
        const ALLOWED = [
            'GROQ_API_KEY', 'GROQ_MODEL', 'NTFY_TOPIC', 'NTFY_TITLE',
            'NTFY_PRIORITY', 'DEFAULT_MESSAGE_LIMIT', 'TUTORIAL_SEEN',
        ];
        for (const key of ALLOWED) {
            if (updates[key] !== undefined) {
                if (key === 'GROQ_API_KEY' && String(updates[key]).trim() === '***') continue;
                this.userSettings[key] = updates[key];
            }
        }
        await mkdir(dirname(this.settingsFile), { recursive: true });
        await writeFile(this.settingsFile, JSON.stringify(this.userSettings, null, 2), 'utf-8');
    }

    async resetOnboardingSettings() {
        delete this.userSettings.GROQ_API_KEY;
        delete this.userSettings.NTFY_TOPIC;
        delete this.userSettings.TUTORIAL_SEEN;
        await mkdir(dirname(this.settingsFile), { recursive: true });
        await writeFile(this.settingsFile, JSON.stringify(this.userSettings, null, 2), 'utf-8');
    }

    // ── Groq client ───────────────────────────────────────────────────────────
    getGroqClient() {
        const apiKey = String(this.getSetting('GROQ_API_KEY') || '').trim();
        if (!apiKey) {
            throw new Error('GROQ_API_KEY is missing. Open Settings and save your Groq API key.');
        }
        if (!this.groq || this.groqKey !== apiKey) {
            this.groq = new Groq({ apiKey });
            this.groqKey = apiKey;
        }
        return this.groq;
    }

    // ── Logging ───────────────────────────────────────────────────────────────
    emit(level, message) {
        console.log(`[${this.sessionId.slice(0, 8)}] ${message}`);
        const line = `${new Date().toISOString()} [${String(level || 'info').toUpperCase()}] ${message}\n`;
        this.logWriteQueue = this.logWriteQueue
            .then(async () => {
                await mkdir(dirname(this.logFile), { recursive: true });
                await appendFile(this.logFile, line, 'utf-8');
            })
            .catch(() => {});
        this.io.to(this.sessionId).emit('log', { level, message });
    }

    // ── Auth / Chromium cleanup ───────────────────────────────────────────────
    async cleanupChromiumSingletonFiles() {
        const sessionDir = join(process.cwd(), '.wwebjs_auth', `session-${this.sessionId}`);
        for (const file of ['SingletonLock', 'SingletonSocket', 'SingletonCookie']) {
            try { await unlink(join(sessionDir, file)); } catch {}
        }
    }

    async clearAuthStorageWithRetries(maxAttempts = 10) {
        const userAuthDir = join(process.cwd(), '.wwebjs_auth', `session-${this.sessionId}`);
        let lastError = null;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                await rm(userAuthDir, { recursive: true, force: true });
                return;
            } catch (err) {
                lastError = err;
                if (!isRetriableAuthCleanupError(err) || attempt === maxAttempts) throw err;
                await sleep(300 * attempt);
            }
        }
        if (lastError) throw lastError;
    }

    // ── Memory ────────────────────────────────────────────────────────────────
    async loadSummaryMemory() {
        try {
            const raw = await readFile(this.summaryMemoryFile, 'utf-8');
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object') return { chats: {} };
            if (!parsed.chats || typeof parsed.chats !== 'object') parsed.chats = {};
            return parsed;
        } catch {
            return { chats: {} };
        }
    }

    async getCachedChatsForApi() {
        const memory = await this.loadSummaryMemory();
        const directory = memory.chatDirectory || {};
        return Object.values(directory)
            .filter(entry => entry?.chatId)
            .sort((a, b) => new Date(b?.updatedAt || 0) - new Date(a?.updatedAt || 0))
            .map(entry => ({
                id: entry.chatId,
                name: entry.chatName || entry.chatId,
                isGroup: !!entry.isGroup,
                unreadCount: 0,
                lastMessage: '',
                timestamp: entry.updatedAt || null,
            }));
    }

    async getChatsForApi() {
        if (this.status !== 'connected') {
            return { chats: [], status: 'disconnected' };
        }

        try {
            const chats = await withTimeout(this.client.getChats(), 15_000, 'api getChats');
            const payload = chats.slice(0, 100).map(c => ({
                id: c.id._serialized,
                name: c.name || c.id.user,
                isGroup: c.isGroup,
                unreadCount: c.unreadCount,
                lastMessage: c.lastMessage?.body?.slice(0, 80) || '',
                timestamp: c.timestamp,
            }));

            void Promise.all(chats.map(ch => this.rememberChatDirectory(ch, []))).catch(() => {});

            return { chats: payload, status: 'connected', stale: false };
        } catch (err) {
            this.emit('error', `[API] getChats failed, using cached chat directory: ${err.message}`);
            const cachedChats = await this.getCachedChatsForApi();
            return {
                chats: cachedChats,
                status: 'connected',
                stale: true,
            };
        }
    }

    async saveSummaryMemory(memory) {
        await mkdir(dirname(this.summaryMemoryFile), { recursive: true });
        await writeFile(this.summaryMemoryFile, JSON.stringify(memory, null, 2), 'utf-8');
    }

    async queueMemoryUpdate(updater) {
        this.memoryWriteQueue = this.memoryWriteQueue
            .then(async () => {
                const memory = await this.loadSummaryMemory();
                await updater(memory);
                await this.saveSummaryMemory(memory);
            })
            .catch(err => this.emit('error', `[MEMORY] Failed: ${err.message}`));
        return this.memoryWriteQueue;
    }

    async getChatMemory(chatId) {
        const memory = await this.loadSummaryMemory();
        return memory.chats?.[chatId] || null;
    }

    async loadMessageCache(chatId) {
        const memory = await this.loadSummaryMemory();
        return memory.chats?.[chatId]?.messageCache || null;
    }

    async saveMessageCache(chatId, payload) {
        if (!chatId || !payload) return;
        await this.queueMemoryUpdate(async (memory) => {
            const chats = memory.chats || (memory.chats = {});
            const entry = chats[chatId] || { chatName: '', participants: [], summaries: [], updatedAt: null };
            entry.messageCache = payload;
            chats[chatId] = entry;
        });
    }

    async rememberChatDirectory(chat, participants = []) {
        if (!chat?.id?._serialized) return;
        const chatId   = chat.id._serialized;
        const chatName = chat.name || chat.id.user || '';
        await this.queueMemoryUpdate(async (memory) => {
            const directory = memory.chatDirectory || (memory.chatDirectory = {});
            const names     = memory.chatNames    || (memory.chatNames    = {});
            const entry = directory[chatId] || { chatId, chatName, isGroup: !!chat.isGroup, phones: [], updatedAt: null };
            entry.chatName  = chatName || entry.chatName;
            entry.isGroup   = !!chat.isGroup;
            entry.updatedAt = new Date().toISOString();
            const merged = new Set(entry.phones || []);
            for (const p of participants) { if (p && typeof p === 'string') merged.add(p); }
            entry.phones = [...merged].slice(0, 200);
            directory[chatId] = entry;
            const normalized = normalizeName(chatName);
            if (normalized) names[normalized] = chatId;
        });
    }

    async findChatByNameFromMemory(c, groupName) {
        const memory    = await this.loadSummaryMemory();
        const names     = memory.chatNames    || {};
        const directory = memory.chatDirectory || {};
        const normalized = normalizeName(groupName);

        const exactId = names[normalized];
        if (exactId) {
            try { return await withTimeout(c.getChatById(exactId), 15_000, 'getChatById memory exact'); } catch {}
        }
        const partial = Object.values(directory).find(e => normalizeName(e?.chatName).includes(normalized));
        if (partial?.chatId) {
            try { return await withTimeout(c.getChatById(partial.chatId), 15_000, 'getChatById memory partial'); } catch {}
        }
        return null;
    }

    async getGeneralMemoryLines(chatId) {
        if (!chatId) return [];
        const memory = await this.loadSummaryMemory();
        const turns = memory?.chats?.[chatId]?.generalQa?.turns;
        if (!Array.isArray(turns) || turns.length === 0) return [];

        const maxTurns = Math.max(2, parseInt(this.getSetting('GENERAL_PERSISTENT_CONTEXT_TURNS', '12')) || 12);
        const selected = turns.slice(-maxTurns);
        const lines = [];
        for (const t of selected) {
            const sender = t?.sender || 'User';
            const userText = String(t?.userText || '').trim();
            const answerText = String(t?.answerText || '').trim();
            if (userText) lines.push(`${sender}: ${userText}`);
            if (answerText) lines.push(`Assistant: ${answerText}`);
        }
        return lines;
    }

    async rememberGeneralTurn({ chatId, chatName = '', sender = 'User', userText = '', answerText = '' }) {
        if (!chatId) return;
        const cleanUserText = String(userText || '').trim();
        const cleanAnswerText = String(answerText || '').trim();
        if (!cleanUserText && !cleanAnswerText) return;

        const maxTurns = Math.max(10, parseInt(this.getSetting('GENERAL_PERSISTENT_MEMORY_TURNS', '60')) || 60);
        await this.queueMemoryUpdate(async (memory) => {
            const chats = memory.chats || (memory.chats = {});
            const entry = chats[chatId] || { chatName: chatName || '', participants: [], summaries: [], updatedAt: null };
            entry.chatName = chatName || entry.chatName;
            const generalQa = entry.generalQa || { turns: [], updatedAt: null };
            generalQa.turns = Array.isArray(generalQa.turns) ? generalQa.turns : [];
            generalQa.turns.push({
                at: new Date().toISOString(),
                sender: String(sender || 'User'),
                userText: cleanUserText,
                answerText: cleanAnswerText,
            });
            generalQa.turns = generalQa.turns.slice(-maxTurns);
            generalQa.updatedAt = new Date().toISOString();
            entry.generalQa = generalQa;
            entry.updatedAt = new Date().toISOString();
            chats[chatId] = entry;
        });
    }

    formatMemoryForPrompt(chatMemory) {
        if (!chatMemory) return [];
        const lines = [];
        const participants = Array.isArray(chatMemory.participants) ? chatMemory.participants.filter(Boolean) : [];
        if (participants.length > 0) {
            lines.push(`[MEMORY] Known participants: ${participants.slice(0, 20).join(', ')}`);
        }
        const summaries = Array.isArray(chatMemory.summaries) ? chatMemory.summaries : [];
        if (summaries.length > 0) {
            lines.push('[MEMORY] Previous summaries from this chat:');
            for (const s of summaries.slice(-3)) {
                const stamp = s.at ? new Date(s.at).toISOString() : 'unknown-time';
                lines.push(`[MEMORY] ${stamp}: ${trimTo(s.text || '', 260)}`);
            }
        }
        return lines;
    }

    async rememberChatSummary({ chatId, chatName, participants, summary }) {
        if (!chatId || !summary) return;
        const MAX_STORED = parseInt(this.getSetting('MAX_STORED_SUMMARIES_PER_CHAT', '10'));
        await this.queueMemoryUpdate(async (memory) => {
            const chats    = memory.chats || (memory.chats = {});
            const existing = chats[chatId] || { chatName: chatName || '', participants: [], summaries: [], updatedAt: null };
            existing.chatName = chatName || existing.chatName || '';
            const mergedParticipants = new Set([...(existing.participants || [])]);
            for (const p of participants || []) { if (p && typeof p === 'string') mergedParticipants.add(p); }
            existing.participants = [...mergedParticipants].slice(0, 50);
            existing.summaries = [
                ...(existing.summaries || []),
                { at: new Date().toISOString(), text: trimTo(summary, 1200) },
            ].slice(-Math.max(1, MAX_STORED));
            existing.updatedAt = new Date().toISOString();
            chats[chatId] = existing;
        });
    }

    // ── Media ─────────────────────────────────────────────────────────────────
    async describeImageForContext(media) {
        const ENABLE_MEDIA = (this.getSetting('ENABLE_MEDIA_ANALYSIS', 'true')).toLowerCase() !== 'false';
        const VISION_MODEL  = this.getSetting('GROQ_VISION_MODEL', '');
        const MAX_BYTES     = parseInt(this.getSetting('MEDIA_VISION_MAX_BYTES', '3000000'));

        if (!ENABLE_MEDIA || !VISION_MODEL || !media?.data || !media?.mimetype?.startsWith('image/')) return '';
        if (!SUPPORTED_VISION_MIME_TYPES.has(String(media.mimetype).toLowerCase())) return '';
        const normalizedBase64 = String(media.data).replace(/\s+/g, '');
        if (!/^[A-Za-z0-9+/=]+$/.test(normalizedBase64)) return '';
        if (Math.floor((normalizedBase64.length * 3) / 4) > MAX_BYTES) return '';

        try {
            const response = await withTimeout(
                this.getGroqClient().chat.completions.create({
                    model: VISION_MODEL,
                    messages: [
                        { role: 'system', content: 'Describe this WhatsApp media in one short, factual sentence for chat context. No markdown.' },
                        { role: 'user', content: [
                            { type: 'text', text: 'Describe the key visible content briefly.' },
                            { type: 'image_url', image_url: { url: `data:${media.mimetype};base64,${normalizedBase64}` } },
                        ]},
                    ],
                    temperature: 0.2,
                }),
                45_000, 'Groq vision'
            );
            return sanitizeForWhatsApp(response.choices?.[0]?.message?.content || '');
        } catch (err) {
            if (!String(err.message || '').toLowerCase().includes('invalid image data')) {
                this.emit('error', `[MEDIA] Vision analysis failed: ${err.message}`);
            }
            return '';
        }
    }

    async describeMediaMessage(message, deepAnalyze = true) {
        const type = message.type || 'media';
        let detail = `[MEDIA:${type}]`;
        const body = (message.body || '').trim();
        if (body) detail += ` caption="${trimTo(body, 120)}"`;
        if (!message.hasMedia || !deepAnalyze) return detail;
        try {
            const media = await withTimeout(message.downloadMedia(), 20_000, 'downloadMedia');
            if (media?.mimetype) detail += ` mime=${media.mimetype}`;
            if (media?.filename) detail += ` file=${media.filename}`;
            const vision = await this.describeImageForContext(media);
            if (vision) detail += ` visual="${trimTo(vision, 180)}"`;
        } catch (err) {
            detail += ' media=unavailable';
            this.emit('error', `[MEDIA] Failed to read media: ${err.message}`);
        }
        return detail;
    }

    // ── Watchdog & unread sync ────────────────────────────────────────────────
    startWatchdog() {
        if (this.watchdogTimer) clearInterval(this.watchdogTimer);
        this.watchdogTimer = setInterval(async () => {
            if (this.status !== 'connected' || this.restarting) return;
            try {
                const state = await withTimeout(this.client.getState(), WATCHDOG_TIMEOUT, 'watchdog getState');
                this.emit('info', `[WATCHDOG] Client alive — state: ${state}`);
            } catch (err) {
                this.emit('error', `[WATCHDOG] Client unresponsive (${err.message}) — restarting...`);
                this.restartClient();
            }
        }, WATCHDOG_INTERVAL);
    }

    async syncUnreadSummaryBuckets() {
        if (this.status !== 'connected' || this.restarting) return;
        const AUTO_THRESHOLD = parseInt(this.getSetting('AUTO_SUMMARY_THRESHOLD', '100'));
        try {
            const chats = await withTimeout(this.client.getChats(), 30_000, 'sync unread getChats');
            for (const chat of chats) {
                if (!chat.isGroup) continue;
                const chatId = chat.id?._serialized;
                if (!chatId) continue;
                const unread       = Number(chat.unreadCount || 0);
                const actualBucket = Math.floor(unread / AUTO_THRESHOLD);
                const storedBucket = this.unreadSummaryBuckets.get(chatId) || 0;
                if (storedBucket !== actualBucket) {
                    this.unreadSummaryBuckets.set(chatId, actualBucket);
                    if (storedBucket > actualBucket) {
                        this.emit('info', `[AUTO] Reset unread state for "${chat.name || chat.id.user}" -> unread=${unread}`);
                    }
                }
            }
        } catch (err) {
            if (this.restarting || isTargetClosedError(err)) return;
            this.emit('error', `[AUTO] Failed syncing unread counts: ${err.message}`);
        }
    }

    startUnreadSync() {
        if (this.unreadSyncTimer) clearInterval(this.unreadSyncTimer);
        this.unreadSyncTimer = setInterval(() => this.syncUnreadSummaryBuckets(), UNREAD_SYNC_INTERVAL);
    }

    resetUnreadCount(chatId) {
        this.unreadSummaryBuckets.delete(chatId);
    }

    scheduleRestart(source = 'INIT', delayMs = 10_000) {
        if (this.restarting || this.restartTimer) return;
        this.restartTimer = setTimeout(() => {
            this.restartTimer = null;
            this.restartClient(source);
        }, delayMs);
    }

    beginClientInitialisation(source = 'INIT') {
        this.cleanupChromiumSingletonFiles().finally(() =>
            this.client.initialize().catch(err => {
                const detail = isTargetClosedError(err)
                    ? `${err.message} — Chromium navigated during WhatsApp boot`
                    : err.message;
                this.emit('error', `[${source}] initialize() failed: ${detail} — retrying in 10 s...`);
                this.scheduleRestart(source, 10_000);
            })
        );
    }

    // ── Client restart ────────────────────────────────────────────────────────
    async restartClient(source = 'WATCHDOG') {
        if (this.restarting) return;
        this.restarting = true;
        if (this.restartTimer) {
            clearTimeout(this.restartTimer);
            this.restartTimer = null;
        }
        this.status = 'loading';
        this.emit('error', `[${source}] Destroying stale client...`);

        if (this.watchdogTimer) { clearInterval(this.watchdogTimer); this.watchdogTimer = null; }
        if (this.unreadSyncTimer) { clearInterval(this.unreadSyncTimer); this.unreadSyncTimer = null; }

        const browserProc = this.client?.pupBrowser?.process();
        if (browserProc && !browserProc.killed) {
            try { browserProc.kill(); } catch {}
        }
        try { await this.client.destroy(); } catch {}
        this.client = null;
        await this.cleanupChromiumSingletonFiles();

        setTimeout(() => {
            this.restarting = false;
            this.emit('info', `[${source}] Re-initialising WhatsApp client...`);
            this.client = this.createAndBindClient();
            this.beginClientInitialisation('INIT');
        }, 5_000);
    }

    // ── Client factory ────────────────────────────────────────────────────────
    createAndBindClient() {
        const self = this;
        let sessionIsAuthenticated = false;
        const c = new Client({
            authStrategy: new LocalAuth({ clientId: this.sessionId }),
            puppeteer: {
                executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--no-first-run',
                ],
            },
        });

        c.on('qr', qr => {
            if (sessionIsAuthenticated) {
                self.emit('info', '[QR] Ignoring late QR event because session is already authenticated.');
                return;
            }
            self.status = 'qr';
            self.qr = qr;
            if (SHOW_TERMINAL_QR) qrcode.generate(qr, { small: true });
            self.io.to(self.sessionId).emit('qr', qr);
        });

        c.on('authenticated', () => {
            sessionIsAuthenticated = true;
            self.qr = null;
            self.status = 'loading';
            self.emit('success', '[STATUS] WhatsApp session authenticated');
            self.io.to(self.sessionId).emit('status', 'loading');
        });

        c.on('ready', () => {
            sessionIsAuthenticated = true;
            self.status = 'connected';
            self.qr = null;
            self.emit('success', '[STATUS] WhatsApp client is ready');
            self.io.to(self.sessionId).emit('ready');
            self.startWatchdog();
            self.startUnreadSync();
            self.syncUnreadSummaryBuckets();
            if (c.pupPage) {
                c.pupPage.on('crash', () => {
                    self.emit('error', '[PUPPETEER] Page crashed — restarting...');
                    self.restartClient();
                });
                c.pupPage.on('close', () => {
                    if (self.status === 'connected') {
                        self.emit('error', '[PUPPETEER] Page closed unexpectedly — restarting...');
                        self.restartClient();
                    }
                });
            }
        });

        c.on('disconnected', reason => {
            self.emit('error', `[STATUS] WhatsApp client disconnected (${reason}) — restarting in 5 s...`);
            self.restartClient();
        });

        c.on('auth_failure', msg => {
            self.status = 'loading';
            self.emit('error', `[AUTH] Authentication failed: ${msg}`);
        });

        this._attachMessageCreate(c);
        return c;
    }

    // ── Summarise ─────────────────────────────────────────────────────────────
    async summariseChat(chat, limit, detailed = false, sinceMs = null, summarizeAllInWindow = false, timeWindowLabel = '') {
        const DEFAULT_LIMIT  = parseInt(this.getSetting('DEFAULT_MESSAGE_LIMIT', '50'));
        const safeLimit      = Math.max(1, parseInt(limit) || DEFAULT_LIMIT);
        const contextExtra   = Math.max(0, parseInt(this.getSetting('SUMMARY_CONTEXT_EXTRA', '30')));
        const CACHE_TTL      = parseInt(this.getSetting('SUMMARY_FETCH_CACHE_TTL_MS', '120000'));
        const fetchLimit     = safeLimit + contextExtra + 12;
        const windowFetchLimit = Math.max(
            fetchLimit,
            parseInt(this.getSetting('SUMMARY_TIME_WINDOW_FETCH_LIMIT', '500')) || 500
        );
        const effectiveFetchLimit = sinceMs ? windowFetchLimit : fetchLimit;
        const timeWindowMaxMessages = Math.max(
            1,
            parseInt(this.getSetting('SUMMARY_TIME_WINDOW_MAX_MESSAGES', '300')) || 300
        );

        const chatId   = chat.id?._serialized;
        const chatName = chat.name || chat.id?.user || '';
        const chatMemory = chatId ? await this.getChatMemory(chatId) : null;

        let contextMessages = [], targetMessages = [];
        let cachedContextLines = null, cachedTargetLines = null;
        let usedCache = false;
        let rawFetchedCount = 0, afterCommandFilterCount = 0, selectedTargetMessageCount = 0;

        const latestMessageId = await this.getLatestMessageId(chat);
        if (!sinceMs) {
            const runtimeCached = this.runtimeFetchCache.get(chatId);
            if (runtimeCached
                && Date.now() - runtimeCached.cachedAt <= CACHE_TTL
                && runtimeCached.latestMessageId === latestMessageId
                && runtimeCached.limit >= safeLimit) {
                contextMessages = runtimeCached.contextMessages.slice(-contextExtra);
                targetMessages  = runtimeCached.targetMessages.slice(-safeLimit);
                selectedTargetMessageCount = targetMessages.length;
                usedCache = true;
            }

            if (!usedCache && chatId) {
                const persistedCache = await this.loadMessageCache(chatId);
                if (persistedCache
                    && Date.now() - new Date(persistedCache.cachedAt || 0).getTime() <= CACHE_TTL
                    && persistedCache.latestMessageId === latestMessageId
                    && persistedCache.limit >= safeLimit) {
                    cachedContextLines = persistedCache.contextLines || [];
                    cachedTargetLines  = persistedCache.targetLines  || [];
                    usedCache = true;
                }
            }
        }

        if (!usedCache) {
            const allMessages = await withTimeout(chat.fetchMessages({ limit: effectiveFetchLimit }), 45_000, 'fetchMessages');
            rawFetchedCount = allMessages.length;
            let filtered = allMessages.filter(m => !isSummarizeCommand(m.body || ''));
            if (sinceMs) {
                filtered = filtered.filter(m => {
                    const tsMs = messageTimestampMs(m);
                    return tsMs > 0 ? tsMs >= sinceMs : false;
                });
            }

            afterCommandFilterCount = filtered.length;
            if (sinceMs && filtered.length === 0) {
                const label = timeWindowLabel || 'requested time window';
                throw new Error(`[NO_MESSAGES] No messages found for ${label}.`);
            }

            targetMessages  = sinceMs && summarizeAllInWindow
                ? filtered.slice(-timeWindowMaxMessages)
                : filtered.slice(-safeLimit);
            selectedTargetMessageCount = targetMessages.length;
            contextMessages = filtered.slice(0, Math.max(0, filtered.length - targetMessages.length)).slice(-contextExtra);
            const runtimePayload = { cachedAt: Date.now(), latestMessageId, limit: safeLimit, contextMessages, targetMessages };
            if (chatId && !sinceMs) this.runtimeFetchCache.set(chatId, runtimePayload);
        }

        const MAX_MEDIA   = parseInt(this.getSetting('MAX_MEDIA_ANALYSIS_PER_SUMMARY', '12'));
        const ENABLE_MEDIA = (this.getSetting('ENABLE_MEDIA_ANALYSIS', 'true')).toLowerCase() !== 'false';
        const participantsSeen = new Set();
        const contactNameCache = new Map();
        let mediaAnalysedCount = 0;

        const resolveMessages = async (messages, label) => {
            const lines = [];
            for (const message of messages) {
                if (!message.body && !message.hasMedia) continue;
                let contact_name = 'Unknown', phone = '';

                if (message.fromMe) {
                    contact_name = this.client.info?.pushname || this.client.info?.wid?.user || 'Me';
                    phone = extractPhoneFromJid(this.client.info?.wid?._serialized || this.client.info?.wid?.user);
                } else {
                    const contactKey = String(message.author || message.from || 'unknown');
                    const cached = contactNameCache.get(contactKey);
                    if (cached) {
                        contact_name = cached.name; phone = cached.phone;
                    } else {
                        try {
                            const contact = await withTimeout(message.getContact(), 8_000, 'getContact');
                            contact_name = contact.name || contact.pushname || message.author || 'Unknown';
                            phone = extractPhoneFromJid(contact.number || contact.id?._serialized || message.author || message.from);
                        } catch {
                            contact_name = message.author || message.from || 'Unknown';
                            phone = extractPhoneFromJid(message.author || message.from);
                        }
                        contactNameCache.set(contactKey, { name: contact_name, phone });
                    }
                }

                const who = message.fromMe
                    ? contact_name
                    : `${message.author ?? contact_name} aka ${contact_name}`;
                participantsSeen.add(phone ? `${contact_name} (${phone})` : contact_name);

                if (message.body) lines.push(`[${label}] ${who}: ${message.body}`);
                if (message.hasMedia) {
                    const allowDeep = label === 'SUMMARY TARGET' && ENABLE_MEDIA && mediaAnalysedCount < MAX_MEDIA;
                    if (allowDeep) mediaAnalysedCount++;
                    lines.push(`[${label}] ${who}: ${await this.describeMediaMessage(message, allowDeep)}`);
                }
            }
            return lines;
        };

        const contextLines = cachedContextLines || await resolveMessages(contextMessages, 'CONTEXT');
        const targetLines  = cachedTargetLines  || await resolveMessages(targetMessages,  'SUMMARY TARGET');

        if (chatId && !cachedContextLines && !cachedTargetLines) {
            await this.saveMessageCache(chatId, {
                cachedAt: new Date().toISOString(), latestMessageId, limit: safeLimit, contextLines, targetLines,
            });
        }
        if (cachedTargetLines) selectedTargetMessageCount = Math.max(selectedTargetMessageCount, cachedTargetLines.length);

        const message_collection = [...this.formatMemoryForPrompt(chatMemory), ...contextLines, ...targetLines];
        this.emit('info', `[STATUS] Messages fetched${usedCache ? ' (cache)' : ''} — target=${targetLines.length}, context=${contextLines.length}`);
        this.emit('info', `[STATUS] rawFetched=${rawFetchedCount || 'cache'}, afterFilter=${afterCommandFilterCount || 'cache'}, selected=${selectedTargetMessageCount}`);
        if (sinceMs) this.emit('info', `[STATUS] Time window applied: ${timeWindowLabel || 'custom window'}`);
        this.emit('info', '[STATUS] Sending messages to AI...');

        const detailPrefix = detailed
            ? 'Provide a DETAILED, thorough summary covering all decisions, conclusions, questions asked, and important context from the [SUMMARY TARGET] messages. Do not omit anything significant.\n\n'
            : '';

        const ai_response = await withTimeout(
            this.getGroqClient().chat.completions.create({
                model: this.getSetting('GROQ_MODEL', 'llama-3.3-70b-versatile'),
                messages: [
                    { role: 'system', content: detailPrefix + systemPrompt.trim() },
                    { role: 'user',   content: message_collection.join('\n') },
                ],
            }),
            90_000, 'Groq API'
        );

        let summary = sanitizeForWhatsApp(
            ai_response.choices[0].message.content.replace(/<think>.*?<\/think>/gs, '').trim()
        );

        if (isNoImportantUpdatesSummary(summary)) {
            this.emit('info', '[STATUS] Strict summary returned no-important-updates; retrying with relaxed recap prompt...');
            const relaxed = await withTimeout(
                this.getGroqClient().chat.completions.create({
                    model: this.getSetting('GROQ_MODEL'),
                    messages: [
                        {
                            role: 'system',
                            content: 'Create a WhatsApp-friendly recap of the [SUMMARY TARGET] messages. Include normal conversation highlights, notable opinions, and any key moments even if no formal decision was made. Use short bullets. Do not say that there were no important updates.',
                        },
                        { role: 'user', content: message_collection.join('\n') },
                    ],
                    temperature: 0.2,
                }),
                90_000,
                'Groq API relaxed recap'
            );

            const relaxedSummary = sanitizeForWhatsApp(
                String(relaxed?.choices?.[0]?.message?.content || '')
                    .replace(/<think>.*?<\/think>/gs, '')
                    .trim()
            );
            if (relaxedSummary) summary = relaxedSummary;
        }

        await this.rememberChatSummary({ chatId, chatName, participants: [...participantsSeen], summary });
        await this.rememberChatDirectory(chat, [...participantsSeen].map(p => {
            const match = p.match(/\((\d{6,15})\)/);
            return match ? match[1] : '';
        }).filter(Boolean));

        this.emit('success', '[STATUS] Summary generated');
        return summary;
    }

    async getLatestMessageId(chat) {
        try {
            const latest = await withTimeout(chat.fetchMessages({ limit: 1 }), 12_000, 'fetchMessages latest');
            return latest?.[0] ? messageIdOf(latest[0]) : '';
        } catch { return ''; }
    }

    // ── ntfy ──────────────────────────────────────────────────────────────────
    async sendNtfy(summary) {
        const topic = this.getSetting('NTFY_TOPIC');
        if (!topic) { this.emit('error', '[NTFY] No NTFY_TOPIC configured.'); return; }
        try {
            const response = await withTimeout(
                axios.post(topic, summary, {
                    headers: {
                        'Title':    this.getSetting('NTFY_TITLE'),
                        'Priority': this.getSetting('NTFY_PRIORITY'),
                    },
                }),
                15_000, 'ntfy'
            );
            this.emit('success', '[STATUS] Notification sent: ' + response.data.message);
        } catch (error) {
            this.emit('error', '[STATUS] Error sending notification: ' + error.message);
        }
    }

    // ── General Q&A ───────────────────────────────────────────────────────────
    async buildGeneralContext(chat, currentMessageId = '') {
        const contextLimit = Math.max(5, parseInt(this.getSetting('GENERAL_CONTEXT_MESSAGE_LIMIT', '30')) || 30);
        const messages = await withTimeout(chat.fetchMessages({ limit: contextLimit + 8 }), 30_000, 'fetchMessages general context');

        const lines = [];
        for (const m of messages) {
            const body = String(m?.body || '').trim();
            if (!body) continue;
            if (isGeneralCommand(body) || isSummarizeCommand(body)) continue;
            if (currentMessageId && messageIdOf(m) === currentMessageId) continue;

            let who = 'User';
            if (m.fromMe) {
                who = 'Me';
            } else if (chat?.isGroup) {
                const phone = extractPhoneFromJid(m.author || m.from);
                who = phone ? `Participant ${phone}` : 'Participant';
            }
            lines.push(`${who}: ${body}`);
        }
        return lines.slice(-contextLimit);
    }

    async answerGeneralQuestion(question, chat = null, currentMessageId = '') {
        const prompt = String(question || '').trim();
        if (!prompt) return 'Usage: !general <your question>';
        const targetWordCount = extractRequestedWordCount(prompt);

        let contextLines = [];
        let persistentLines = [];
        if (chat) {
            try { contextLines = await this.buildGeneralContext(chat, currentMessageId); }
            catch (err) { this.emit('error', '[GENERAL CONTEXT ERROR] ' + err.message); }
            try { persistentLines = await this.getGeneralMemoryLines(chat.id?._serialized || ''); }
            catch (err) { this.emit('error', '[GENERAL MEMORY READ ERROR] ' + err.message); }
        }

        const userPrompt = (persistentLines.length > 0 || contextLines.length > 0)
            ? `${persistentLines.length > 0 ? `Persistent memory from previous general chats (oldest to newest):\n${persistentLines.join('\n')}\n\n` : ''}${contextLines.length > 0 ? `Recent chat context (oldest to newest):\n${contextLines.join('\n')}\n\n` : ''}Current question: ${prompt}`
            : prompt;

        const ai_response = await withTimeout(
            this.getGroqClient().chat.completions.create({
                model: this.getSetting('GROQ_MODEL'),
                messages: [
                    { role: 'system', content: 'Answer the user question directly. Use recent chat context when it is relevant. If context is missing, say so briefly. Output only the answer text with no preamble, no labels, and no extra commentary.' },
                    { role: 'user',   content: userPrompt },
                ],
                temperature: 0.2,
            }),
            90_000, 'Groq API general'
        );

        let answer = sanitizeForWhatsApp(
            String(ai_response?.choices?.[0]?.message?.content || '')
                .replace(/<think>.*?<\/think>/gs, '').trim()
        );

        if (targetWordCount) {
            const currentCount = getWordCount(answer);
            if (currentCount !== targetWordCount) {
                try {
                    const rewrite = await withTimeout(
                        this.getGroqClient().chat.completions.create({
                            model: this.getSetting('GROQ_MODEL'),
                            messages: [
                                { role: 'system', content: `Rewrite the answer so it contains exactly ${targetWordCount} words. Return only the rewritten answer text.` },
                                { role: 'user',   content: answer },
                            ],
                            temperature: 0,
                        }),
                        60_000, 'Groq API general rewrite'
                    );
                    answer = sanitizeForWhatsApp(
                        String(rewrite?.choices?.[0]?.message?.content || '')
                            .replace(/<think>.*?<\/think>/gs, '').trim()
                    );
                } catch {}
                if (getWordCount(answer) !== targetWordCount) answer = forceWordCount(answer, targetWordCount);
            }
        }
        return answer;
    }

    // ── Command gating ────────────────────────────────────────────────────────
    isCommandAllowedForMessage(msg, chat = null) {
        if (msg?.fromMe) return true;

        // In group chats, allow any participant to run bot commands.
        if (chat?.isGroup) return true;

        // In direct chats, allow any sender to run bot commands.
        if (chat && !chat.isGroup) return true;

        const ALLOW_PUBLIC = (process.env.ALLOW_PUBLIC_COMMANDS || 'false').toLowerCase() === 'true';
        if (!ALLOW_PUBLIC) return false;
        const ALLOWED_PHONES = new Set(
            String(process.env.ALLOWED_COMMAND_PHONES || '').split(',').map(v => v.trim()).filter(Boolean)
        );
        if (ALLOWED_PHONES.size === 0) return true;
        const phone = extractPhoneFromJid(msg?.author || msg?.from);
        return phone ? ALLOWED_PHONES.has(phone) : false;
    }

    // ── Message handler ───────────────────────────────────────────────────────
    _attachMessageCreate(c) {
        c.on('message_create', async (msg) => {
            const AUTO_THRESHOLD = parseInt(this.getSetting('AUTO_SUMMARY_THRESHOLD', '100'));

            if (!msg.fromMe) {
                let chat;
                try { chat = await withTimeout(msg.getChat(), 15_000, 'getChat'); }
                catch (err) { this.emit('error', '[AUTO] Failed to get chat: ' + err.message); return; }

                let senderName = 'Unknown', senderPhone = '';
                try {
                    const contact = await withTimeout(msg.getContact(), 8_000, 'getContact');
                    senderName  = contact.name || contact.pushname || msg.author || 'Unknown';
                    senderPhone = extractPhoneFromJid(contact.number || contact.id?._serialized || msg.author || msg.from);
                } catch {}
                this.emit('info', `[MSG] "${chat.name || chat.id.user}" from ${senderName}: ${msg.body}`);
                await this.rememberChatDirectory(chat, senderPhone ? [senderPhone] : []);

                if (msg.body.toLowerCase().trim() === 'whatsapp summary') {
                    this.emit('info', `[TRIGGER] "whatsapp summary" requested in "${chat.name || chat.id.user}"`);
                    try {
                        const summary = await withTimeout(
                            this.summariseChat(chat, parseInt(this.getSetting('DEFAULT_MESSAGE_LIMIT', '50'))),
                            120_000, 'summariseChat trigger'
                        );
                        await withTimeout(chat.sendMessage(summary), 15_000, 'sendMessage');
                        this.io.to(this.sessionId).emit('summary_done', summary);
                    } catch (err) { this.emit('error', '[TRIGGER ERROR] ' + err.message); }
                    return;
                }

                if (chat.isGroup) {
                    const id = chat.id._serialized;
                    let latestChat = chat;
                    try { latestChat = await withTimeout(c.getChatById(id), 15_000, 'getChatById auto'); } catch {}
                    const unread     = Number(latestChat.unreadCount || 0);
                    const bucket     = Math.floor(unread / AUTO_THRESHOLD);
                    const lastBucket = this.unreadSummaryBuckets.get(id) || 0;
                    if (bucket === 0) {
                        if (lastBucket !== 0) this.unreadSummaryBuckets.set(id, 0);
                    } else if (bucket > lastBucket) {
                        this.unreadSummaryBuckets.set(id, bucket);
                        this.emit('info', `[AUTO] Threshold hit for "${latestChat.name || chat.name}" (unread=${unread}) — generating summary...`);
                        try {
                            const summary = await withTimeout(
                                this.summariseChat(latestChat, AUTO_THRESHOLD), 120_000, 'summariseChat auto'
                            );
                            const ntfyText = `📋 ${latestChat.name || chat.name}\n\n${summary}`;
                            await withTimeout(this.sendNtfy(ntfyText), 20_000, 'sendNtfy auto');
                            this.io.to(this.sessionId).emit('summary_done', summary);
                        } catch (err) {
                            this.unreadSummaryBuckets.set(id, Math.max(0, bucket - 1));
                            this.emit('error', '[AUTO ERROR] ' + err.message);
                        }
                    }
                }
            }

            if (msg.fromMe) {
                try {
                    const chat = await withTimeout(msg.getChat(), 15_000, 'getChat fromMe');
                    this.emit('info', `[YOU → "${chat.name || chat.id.user}"]: ${msg.body}`);
                } catch {}
            }

            if (isGeneralCommand(msg.body)) {
                try {
                    const replyChat = await withTimeout(msg.getChat(), 15_000, 'getChat general reply');
                    if (!this.isCommandAllowedForMessage(msg, replyChat)) return;
                    const question  = String(msg.body || '').trim().slice('!general'.length).trim();
                    try { await replyChat.sendStateTyping(); } catch {}
                    const answer    = await this.answerGeneralQuestion(question, replyChat, messageIdOf(msg));
                    try { await replyChat.clearState(); } catch {}
                    await withTimeout(replyChat.sendMessage(answer), 20_000, 'sendMessage general');

                    const senderPhone = extractPhoneFromJid(msg.author || msg.from);
                    const senderLabel = senderPhone ? `User ${senderPhone}` : 'User';
                    await this.rememberGeneralTurn({
                        chatId: replyChat.id?._serialized || '',
                        chatName: replyChat.name || replyChat.id?.user || '',
                        sender: senderLabel,
                        userText: question,
                        answerText: answer,
                    });
                } catch (err) { this.emit('error', '[GENERAL ERROR] ' + err.message); }
                return;
            }

            if (isSummarizeCommand(msg.body)) {
                const raw      = msg.body;
                const detailed = raw.trimEnd().toLowerCase().endsWith(' detail');
                const stripped = detailed ? raw.trimEnd().slice(0, -7).trimEnd() : raw;
                const commandBody = stripped.replace(/^\S+\s*/, '').trim();
                const timeWindow = parseSummaryTimeWindow(commandBody);
                const commandBodyWithoutWindow = timeWindow ? timeWindow.remaining : commandBody;
                const parts = commandBodyWithoutWindow ? commandBodyWithoutWindow.split(/\s+/) : [];

                let targetChat, number_of_messages;
                let groupName = '';
                let explicitLimit = null;
                const defaultMessageLimit = parseInt(this.getSetting('DEFAULT_MESSAGE_LIMIT', '50'));
                const replyChat = await withTimeout(msg.getChat(), 15_000, 'getChat cmd reply');
                if (!this.isCommandAllowedForMessage(msg, replyChat)) return;

                if (parts.length === 1 && !isNaN(parts[0])) {
                    explicitLimit = parseInt(parts[0], 10);
                }

                if (!commandBodyWithoutWindow) {
                    targetChat = replyChat;
                    number_of_messages = defaultMessageLimit;
                } else if (explicitLimit !== null) {
                    targetChat = replyChat;
                    number_of_messages = explicitLimit;
                } else {
                    const lastArg = parts[parts.length - 1];
                    const hasCount = !isNaN(lastArg) && parts.length > 1;
                    number_of_messages = hasCount ? parseInt(lastArg, 10) : defaultMessageLimit;
                    groupName = hasCount ? parts.slice(0, -1).join(' ') : commandBodyWithoutWindow;
                }

                // Only the bot owner (fromMe) can target a named chat/group.
                if (!msg.fromMe && groupName) {
                    await withTimeout(
                        replyChat.sendMessage('You can only summarize this current chat. Targeting another chat by name is not allowed.'),
                        20_000,
                        'sendMessage cmd denied'
                    );
                    return;
                }

                if (groupName) {
                    this.emit('info', `[STATUS] Searching for chat: "${groupName}"`);
                    targetChat = await this.findChatByNameFromMemory(c, groupName);
                    if (!targetChat) {
                        const allChats = await withTimeout(this.client.getChats(), 30_000, 'getChats');
                        targetChat = allChats.find(ch => ch.name?.toLowerCase() === groupName.toLowerCase())
                            || allChats.find(ch => ch.name?.toLowerCase().includes(groupName.toLowerCase()));
                        for (const ch of allChats) await this.rememberChatDirectory(ch, []);
                    }
                    if (!targetChat) { this.emit('error', `[ERROR] No chat found matching "${groupName}"`); return; }
                    this.emit('info', `[STATUS] Found chat: "${targetChat.name}"`);
                }

                try {
                    const summarizeAllInWindow = !!timeWindow && explicitLimit === null;
                    try { await replyChat.sendStateTyping(); } catch {}
                    const summary = await withTimeout(
                        this.summariseChat(
                            targetChat,
                            number_of_messages,
                            detailed,
                            timeWindow?.sinceMs || null,
                            summarizeAllInWindow,
                            timeWindow?.label || ''
                        ),
                        120_000,
                        'summariseChat cmd'
                    );
                    try { await replyChat.clearState(); } catch {}
                    await withTimeout(replyChat.sendMessage(summary), 20_000, 'sendMessage cmd');
                    this.io.to(this.sessionId).emit('summary_done', summary);
                } catch (err) {
                    this.emit('error', '[ERROR] ' + err.message);
                    if (String(err?.message || '').includes('[NO_MESSAGES]')) {
                        try {
                            const label = timeWindow?.label || 'the requested time range';
                            await withTimeout(replyChat.sendMessage(`No messages found in ${label}.`), 20_000, 'sendMessage no messages');
                        } catch {}
                    }
                }
            }
        });
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    async start() {
        await this.loadSettings();
        this.client = this.createAndBindClient();
        this.beginClientInitialisation('INIT');
    }

    async logout() {
        this.emit('info', '[LOGOUT] Logging out WhatsApp session...');
        this.restarting = true;

        if (this.watchdogTimer)   { clearInterval(this.watchdogTimer);   this.watchdogTimer   = null; }
        if (this.unreadSyncTimer) { clearInterval(this.unreadSyncTimer); this.unreadSyncTimer = null; }
        if (this.restartTimer)    { clearTimeout(this.restartTimer);      this.restartTimer    = null; }

        let didLogoutGracefully = false;
        try {
            await withTimeout(this.client.logout(), 20_000, 'logout');
            didLogoutGracefully = true;
        } catch (err) { this.emit('error', `[LOGOUT] logout() failed: ${err.message}`); }

        if (!didLogoutGracefully) {
            const browserProc = this.client?.pupBrowser?.process();
            if (browserProc && !browserProc.killed) {
                try { browserProc.kill(); } catch {}
            }
        }

        try { await withTimeout(this.client.destroy(), 20_000, 'destroy after logout'); }
        catch (err) { this.emit('error', `[LOGOUT] destroy() failed: ${err.message}`); }

        try { await this.clearAuthStorageWithRetries(); }
        catch (err) { this.emit('error', `[LOGOUT] Failed to clear auth storage: ${err.message}`); }

        try { await this.resetOnboardingSettings(); }
        catch (err) { this.emit('error', `[LOGOUT] Failed to reset onboarding settings: ${err.message}`); }

        this.unreadSummaryBuckets.clear();
        this.runtimeFetchCache.clear();
        await this.cleanupChromiumSingletonFiles();
        this.status = 'loading';
        this.qr = null;
        this.io.to(this.sessionId).emit('status', 'loading');

        await sleep(1500);
        this.restarting = false;
        this.client = this.createAndBindClient();
        this.beginClientInitialisation('LOGOUT');
    }
}
