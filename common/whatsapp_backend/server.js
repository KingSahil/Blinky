import 'dotenv/config';
import express from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import cors from 'cors';
import { existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { initSessionManager, getOrCreateSession, getSession } from './SessionManager.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const httpServer = createServer(app);

// CORS: default to same-origin / no-origin only. A wildcard `*` default would let
// any website the user visits issue cross-origin requests to this server (reading
// chat lists, marking chats read, triggering summaries). Cross-origin access is
// only granted for explicitly listed origins via ALLOWED_ORIGINS.
const allowedOrigins = process.env.ALLOWED_ORIGINS
    ? process.env.ALLOWED_ORIGINS.split(',').map(s => s.trim()).filter(Boolean)
    : [];
const corsOptions = {
    origin(origin, callback) {
        // No Origin header = same-origin/curl/native client → allow.
        if (!origin) return callback(null, true);
        if (allowedOrigins.includes(origin)) return callback(null, true);
        return callback(new Error('Not allowed by CORS'));
    },
    methods: ['GET', 'POST'],
};

const io = new Server(httpServer, {
    cors: corsOptions,
});

app.use(cors(corsOptions));
app.use(express.json());

const DEFAULT_SESSION_ID = 'blinky-default-session';

// Serve built frontend
const frontendDistCandidates = [
    path.join(__dirname, 'frontend', 'dist'),
    path.join(__dirname, 'frontend'),
    path.join(process.cwd(), 'frontend', 'dist'),
    path.join(__dirname, '..', 'frontend', 'dist'),
];
const frontendDist = frontendDistCandidates.find((p) => existsSync(path.join(p, 'index.html'))) || frontendDistCandidates[0];
app.use(express.static(frontendDist));

// ── Session middleware ─────────────────────────────────────────────────────────
// Validates X-Session-Id header and attaches the session to req.session.
function isValidSessionId(id) {
    return typeof id === 'string'
        && id.length >= 8
        && id.length <= 64
        && /^[a-zA-Z0-9_-]+$/.test(id);
}

function requireSession(req, res, next) {
    const sessionId = DEFAULT_SESSION_ID;
    const session = getSession(sessionId);
    if (!session) {
        return res.status(404).json({ error: 'Session not found. Reconnect to create one.' });
    }
    req.session = session;
    next();
}

// ── REST API ──────────────────────────────────────────────────────────────────

// Register / ensure a session exists.
// Always use the default session ID to share between app and web
app.post('/api/sessions', async (req, res) => {
  try {
    const sessionId = DEFAULT_SESSION_ID;
    const { isNew } = await getOrCreateSession(sessionId);
    res.json({ sessionId, isNew });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/status', requireSession, (req, res) => {
  res.json(req.session.getStatus());
});

app.get('/api/chats', requireSession, async (req, res) => {
  try {
        const result = await req.session.getChatsForApi();
        if (result?.status === 'disconnected') {
            return res.status(503).json({ error: 'WhatsApp not connected yet' });
        }
        res.json(result.chats || []);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/debug-chats', requireSession, async (req, res) => {
  try {
        const results = await req.session.client.pupPage.evaluate(async () => {
            const id = '120363426466297788@g.us';
            try {
                const collections = window.require ? window.require('WAWebCollections') : null;
                const chat = collections?.Chat?.get(id) || window.Store?.Chat?.get(id);
                if (!chat) return { error: "Chat not in collections" };
                const msgs = chat.msgs?.getModelsArray() || [];
                return {
                    id: chat.id?._serialized,
                    name: chat.name,
                    msgCount: msgs.length,
                    firstMsg: msgs[0]?.body,
                    lastMsg: msgs[msgs.length - 1]?.body,
                };
            } catch (e) {
                return { error: e.stack || e.message || String(e) };
            }
        });
        res.json(results);
  } catch (err) {
    res.status(500).json({ error: err.stack || err.message });
  }
});

app.post('/api/chats/:id/read', requireSession, async (req, res) => {
    try {
        const { status } = req.session.getStatus();
        if (status !== 'connected') return res.status(503).json({ error: 'WhatsApp not connected yet' });
        const chats = await req.session.client.getChats();
        const chat = chats.find(c => c.id._serialized === req.params.id);
        if (!chat) return res.status(404).json({ error: 'Chat not found' });
        await chat.sendSeen();
        req.session.resetUnreadCount(req.params.id);
        res.json({ ok: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/summarise', requireSession, async (req, res) => {
    try {
        const { chatId, limit = 50 } = req.body;
        if (!chatId) return res.status(400).json({ error: 'chatId required' });
        const chat = await req.session.getChatInstance(chatId);
        if (!chat) return res.status(404).json({ error: 'Chat not found' });
        const summary = await req.session.summariseChat(chat, parseInt(limit));
        // Ntfy push is fire-and-forget; failures must not fail the request, and
        // it is only sent when explicitly enabled (guards against surprise spam).
        if (process.env.NTFY_ENABLED === 'true') {
            req.session.sendNtfy(summary).catch((err) => {
                console.error('[SERVER] ntfy push failed:', err?.message || err);
            });
        }
        io.to(req.session.sessionId).emit('summary_done', summary);
        res.json({ summary });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/logout', requireSession, async (req, res) => {
    try {
        await req.session.logout();
        res.json({ ok: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/settings', requireSession, (req, res) => {
    res.json(req.session.getSettingsForApi());
});

app.post('/api/settings', requireSession, async (req, res) => {
    try {
        await req.session.saveSettings(req.body);
        res.json({ ok: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Catch-all: serve React app
app.use((req, res) => {
    res.sendFile(path.join(frontendDist, 'index.html'));
});

// ── Socket.io ─────────────────────────────────────────────────────────────────
// Each socket joins its own session room; events are scoped per-user.
io.on('connection', async (socket) => {
    const sessionId = DEFAULT_SESSION_ID;

    socket.join(sessionId);
    console.log(`[WS] Socket ${socket.id} joined session ${sessionId.slice(0, 8)}...`);

    // Create session if it doesn't exist yet (first-time connection).
    const { session } = await getOrCreateSession(sessionId);
    const { status, qr } = session.getStatus();
    socket.emit('status', status);
    if (status === 'qr' && qr) socket.emit('qr', qr);
    if (status === 'connected') socket.emit('ready');
});

// ── Start ─────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
// Bind loopback by default: the WhatsApp backend serves the local web UI only.
// Set HOST=0.0.0.0 explicitly to expose it (e.g. behind a reverse proxy).
const HOST = process.env.HOST || '127.0.0.1';
httpServer.listen(PORT, HOST, () => {
    console.log(`[SERVER] Running at http://${HOST}:${PORT}`);
});
httpServer.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        const fallback = Number(PORT) + 1;
        console.warn(`[SERVER] Port ${PORT} in use, retrying on ${fallback}...`);
        setTimeout(() => httpServer.listen(fallback, () => {
            console.log(`[SERVER] Running at http://localhost:${fallback}`);
        }), 1000);
    } else {
        throw err;
    }
});

initSessionManager(io).catch(err => console.error('[SERVER] Failed to init session manager:', err));

// ── Graceful shutdown ────────────────────────────────────────────────────────
async function cleanupAndExit() {
    console.log('[SERVER] Shutting down WhatsApp backend...');
    try {
        const session = getSession(DEFAULT_SESSION_ID);
        if (session?.client) {
            try { await session.client.destroy(); } catch {}
        }
        if (session) {
            try { await session.killOrphanedBrowsers(); } catch {}
        }
    } catch {}
    process.exit(0);
}

process.on('SIGINT', cleanupAndExit);
process.on('SIGTERM', cleanupAndExit);

