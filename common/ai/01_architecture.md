# Blinky System Architecture

Blinky is a local-first desktop tutor with a companion mobile remote. The desktop app is built with Tauri 2, React, Rust, and Python. It can guide a user on the visible desktop screen, run a bounded safe-click autopilot loop in web mode, or accept remote WebSocket requests from the mobile app.

## 1. Runtime Surfaces

```text
User
├── Desktop command bar (/command)
│   ├── normal mode
│   │   └── Tauri run_tutor command
│   │       └── python/main.py screen tutor worker
│   │           └── OCR + UIA + LLM + matching
│   │               └── overlay highlight (/overlay)
│   └── globe/web mode
│       └── runAgentQuery -> browser_agent/browser_controller
│           └── visible Microsoft Edge through Playwright
│               └── runTutor observe -> click_screen_point act -> repeat max 5
│       └── run_tutor web_search_enabled -> python/wil pipeline
│           └── SearXNG on localhost:8888 -> retrieved sources -> streamed answer
└── Expo mobile app
    └── ws://<pc>:9001
        └── src-tauri/src/websocket.rs
            └── persistent python/agent_router.py sidecar
                └── safe browser planner + registered/generated browser tools + streamed synthesis
```

## 2. Desktop Screen Tutor Flow

1. `frontend/src/main.tsx` routes `/command` to `CommandBar.tsx` and `/overlay` to `Overlay.tsx`.
2. `CommandBar.tsx` sends `run_tutor` through `frontend/src/lib/tauri.ts`.
3. `src-tauri/src/lib.rs` excludes the command and overlay windows from Windows capture, waits briefly, and spawns `python/main.py`.
4. `python/main.py` may classify the request as text-only, otherwise captures the screen and prints `__BLINKY_CAPTURED__`.
5. Rust sees the marker and immediately restores capture visibility for the Blinky windows.
6. Python resolves active app state, OCR items, UIA controls, prompt output, match attachments, and returns JSON.
7. Rust parses the JSON and emits `blinky://guidance` to the overlay.
8. `Overlay.tsx` maps screenshot-space bounds to CSS pixels and renders the active highlight.
9. On Windows, Rust monitors global clicks/Enter and emits `blinky://global-click` or `blinky://global-enter`.
10. `CommandBar.tsx` records completed progress and re-runs `run_tutor` for the next screen state.

In globe/web mode, `CommandBar.tsx` first runs `runAgentQuery()` so the browser planner can open/search in Edge. It then calls `runAutopilotLoop()`, which repeatedly observes the screen with `runTutor()`, clicks one safe matched target through `click_screen_point`, waits briefly, and observes again. The loop stops at completion, unsafe/missing targets, unchanged repeated targets, or 5 attempts.

When `web_search_enabled` reaches `python/main.py`, the worker can run the Web Intelligence Layer in `python/wil/`. That path plans search queries, queries SearXNG at `http://localhost:8888`, fetches top sources, processes text, and streams status/chunks back through `blinky://tutor-status` and `blinky://tutor-chunk`.

## 3. Remote WebSocket / Agent Flow

At app startup, `src-tauri/src/lib.rs` spawns `websocket::start_websocket_server()`.

```text
Expo app
  -> JSON { requestId, query } or command string
  -> Rust WebSocket server on 0.0.0.0:9001
  -> AgentDaemon starts/reuses python -u python/agent_router.py
  -> line-delimited JSON responses stream back to the phone
```

Direct power commands are `power_off`, `restart`, and `sleep`. Query messages are forwarded to `agent_router.py`, which first tries the safe browser planner, then registered tools, then generated Playwright tools, and finally streams synthesized answers.

See `07_agent_router.md` and `08_mobile_remote.md`.

## 4. Tauri Windows and Events

| Window | Route | Purpose |
| :--- | :--- | :--- |
| `command` | `/command` | Floating command bar, settings, voice controls, status, Action Guide. |
| `overlay` | `/overlay` | Transparent click-through highlight layer. |
| default route | `/` | Fallback `App.tsx` command UI. |

Important events:

| Event | Source | Destination | Purpose |
| :--- | :--- | :--- | :--- |
| `blinky://open-command` | Rust hotkey/tray | command | Reveal and focus input. |
| `blinky://guidance` | Rust or command route | overlay | Send tutor result to render highlights. |
| `blinky://global-click` | Rust Windows polling thread | overlay | Report desktop click coordinates. |
| `blinky://target-clicked` | overlay | command | Mark highlighted step as completed. |
| `blinky://global-enter` | Rust Windows polling thread | app event bus | Advance text-entry steps after Enter. |

Important commands:

| Command | Source | Purpose |
| :--- | :--- | :--- |
| `run_tutor` | frontend -> Rust -> Python | Capture/read the screen and return the next tutor step. |
| `click_screen_point` | frontend -> Rust | Native Windows click at physical screen coordinates for safe autopilot actions. |

## 5. Python Screen Worker Contract

`python/main.py` reads one JSON object from stdin:

```json
{
  "question": "install the Python extension",
  "previous_question": "install the Python extension",
  "progress": {
    "completed_targets": ["Extensions"],
    "completed_instructions": ["Click Extensions."]
  },
  "conversation_history": [
    { "role": "student", "content": "install the Python extension" },
    { "role": "blinky", "content": "Open the Extensions view." }
  ]
}
```

It returns one JSON object:

```json
{
  "summary": "In Visual Studio Code, search for the Python extension.",
  "steps": [
    {
      "step": 1,
      "instruction": "Type Python in the extensions search field.",
      "target_text": "Search Extensions in Marketplace",
      "match": {
        "text": "Search Extensions in Marketplace",
        "x": 82,
        "y": 90,
        "width": 320,
        "height": 30,
        "confidence": 0.9,
        "source": "uia",
        "control_type": "Edit"
      }
    }
  ],
  "active_app": { "title": "...", "process": "...", "supported": true },
  "ocr": { "count": 42, "items": [] },
  "screenshot": {
    "path": "tmp\\captures\\...",
    "width": 1728,
    "height": 1080,
    "screen_width": 2560,
    "screen_height": 1600
  },
  "elapsed_ms": 740,
  "provider": "Groq",
  "warnings": [],
  "is_continuation": false
}
```

## 6. Settings and Environment

Settings are persisted to `.env` through `get_settings` / `save_settings` in Rust.

| Variable | Used by | Notes |
| :--- | :--- | :--- |
| `BLINKY_AI_PROVIDER` | Python/Rust | `ollama` or `groq`. Rust settings default is `groq`; Python defaults to `ollama` if absent. |
| `BLINKY_OLLAMA_URL` | Python | Defaults to `http://localhost:11434/api/generate`. |
| `BLINKY_OLLAMA_MODEL` | Python | Defaults to `gemma4:e4b`. |
| `BLINKY_OLLAMA_TIMEOUT` | Python | Defaults to `35` seconds. |
| `BLINKY_GROQ_URL` | Python | Defaults to OpenAI-compatible Groq chat completions URL. |
| `BLINKY_GROQ_MODEL` | Python | Defaults to `meta-llama/llama-4-scout-17b-16e-instruct`. |
| `BLINKY_GROQ_TIMEOUT` | Python | Defaults to `90` seconds. |
| `GROQ_API_KEY` | Python/Rust settings | Required for Groq. |
| `SARVAM_API_KEY` | Frontend/Rust settings | Required for voice features. |
| `BLINKY_SHORTCUT` | Rust/frontend | `Enter` or `Space`, meaning Ctrl+Shift+Enter or Ctrl+Shift+Space. |
| `BLINKY_BROWSER_CHANNEL` | Python browser controller | Defaults to `msedge`. |
| `BLINKY_BROWSER_HEADLESS` | Python browser controller | Defaults to visible browser mode (`false`). |
| SearXNG local service | Docker Compose | `docker compose up -d searxng`, exposed on port `8888`. |

## 7. Platform Notes

- Windows capture exclusion uses `SetWindowDisplayAffinity` with `WDA_EXCLUDEFROMCAPTURE`.
- Windows global click and Enter detection uses `GetAsyncKeyState` in a background thread.
- Windows autopilot clicking uses `SendInput` and expects physical virtual-desktop coordinates.
- Linux overlay positioning avoids the GNOME top panel by moving the overlay below the panel when `XDG_CURRENT_DESKTOP` contains `GNOME`.
- UIA is Windows-only. On non-Windows, screen understanding relies primarily on screenshot/OCR paths.
- `mobile/AGENTS.md` says Expo docs must be checked before editing mobile code.
