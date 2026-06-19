# Blinky AI Documentation Hub

This folder is the developer and AI-agent map for the Blinky repository. It reflects the current codebase: a Tauri desktop tutor, a bounded screen autopilot loop, desktop computer-use agent actions (open app/shortcut/Spotify track playback), a Python screen-understanding worker, a Python browser-agent sidecar exposed over WebSocket, a SearXNG-backed Web Intelligence Layer, and an Expo mobile remote.

## Reading Order

| File | Purpose |
| :--- | :--- |
| `00_repo_summary.md` | Repository map, setup commands, and guide index. |
| `01_architecture.md` | Desktop architecture, IPC/event flow, autopilot, settings, and platform notes. |
| `02_coordinate_scaling.md` | Screenshot, UIA, overlay, and autopilot click coordinate transforms. |
| `03_matching_heuristics.md` | Target matching, merge rules, post-processing, and autopilot safety gates. |
| `04_ai_inference.md` | Screen tutor prompts, preflight, provider clients, locator fast path, conversation state, and autopilot continuation. |
| `05_sarvam.md` | Sarvam TTS/STT integration used by the desktop command bar. |
| `06_detailed_summaries.md` | Per-file implementation reference for core modules. |
| `07_agent_router.md` | Browser-agent sidecar, Edge controller, generated tools, streaming synthesis, and WebSocket protocol. |
| `08_mobile_remote.md` | Expo mobile remote app, connection lifecycle, PC controls, and remote agent UI. |
| `09_computer_use_and_spotify.md` | Human + AI guide for desktop agent-mode computer-use actions, Spotify playback, and routing boundaries. |
| `files_index.json` | Machine-readable file index for agents and scripts. |

## Current Product Shape

Blinky has four major interaction modes:

1. **Desktop screen tutor**: The Tauri command bar accepts a question, Python captures the active screen, OCR/UIA extract visible controls, an LLM returns the immediate next action, and the overlay highlights the matched UI element.
2. **Desktop agent mode (computer use)**: In agent mode, `python/main.py` can directly execute local actions like opening apps, pressing shortcuts, and playing Spotify tracks via URI resolution, with fallback to screen mode on failures.
3. **Desktop globe/web mode**: The command bar can route web tasks through the Python browser planner, open/search in visible Microsoft Edge through Playwright, then run a bounded observe-act loop that clicks only safe matched targets for up to 5 attempts.
4. **Remote mobile control**: The Expo app connects to the desktop WebSocket server on port `9001`, sends power commands or browser-agent queries, and displays streamed status/results from `python/agent_router.py`.

## Repository Map

```text
c:\projects\Jarvis
├── ai/                  Documentation hub
├── frontend/src/        React/Tauri command bar and overlay views
├── mobile/              Expo remote controller
├── python/              Screen tutor worker, AI clients, OCR/capture, browser agent, router tools
├── scripts/             Setup and Ollama checks
├── shared/              Result schema examples
└── src-tauri/           Rust host, WebSocket server, tray, shortcuts, windows
```

## Common Commands

```powershell
bun install
bun run setup:python
bun run check:ollama
bun run dev
bun run build
```

Local web search:

```powershell
docker compose up -d searxng
```

Mobile app:

```powershell
cd mobile
npm install
npm run start
```

## Key Runtime Defaults

| Setting | Default / Source |
| :--- | :--- |
| Desktop app name | `Blinky` in `src-tauri/tauri.conf.json` |
| Command route | `/command` -> `frontend/src/CommandBar.tsx` |
| Overlay route | `/overlay` -> `frontend/src/Overlay.tsx` |
| WebSocket server | `0.0.0.0:9001` in `src-tauri/src/websocket.rs` |
| AI provider default in Rust settings | `groq` |
| AI provider default in Python client | `ollama` if env is absent |
| Ollama model | `gemma4:e4b` |
| Groq model | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Sarvam TTS/STT | `bulbul:v3` / `saaras:v3` |
| Browser controller | Playwright `chromium.launch(channel="msedge", headless=false)` by default |
| SearXNG URL | `http://localhost:8888` |
| Autopilot attempts | 5 max per command-bar globe/web request |

## Agent Notes

- Treat `CommandBar.tsx` as the primary command UI. `App.tsx` remains as the default route fallback and is less feature-complete.
- Keep the Python screen worker stdout JSON-clean. The only non-JSON stdout marker is `__BLINKY_CAPTURED__`.
- Keep screen-tutor guidance single-step. The frontend advances by re-running the worker after each completed step or after each safe autopilot click.
- Autopilot clicks only matched safe actions. Do not add automatic typing, purchase, login, install, enable, delete, or submit behavior without a separate safety design.
- Desktop computer-use actions are in `python/computer_use/`. Keep these tools narrow, explicit, and safe-failing so unsupported actions fall back to screen guidance.
- Spotify desktop playback (`play ... on Spotify`) is part of computer-use agent mode, not the mobile router path.
- The mobile agent path is separate from the screen-tutor path. It uses WebSocket -> Rust daemon manager -> `python/agent_router.py`, not `run_tutor`.
