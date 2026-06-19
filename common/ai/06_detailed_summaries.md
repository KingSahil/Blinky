# Blinky Per-File Reference

This reference summarizes the files that most often matter when changing Blinky.

## 1. Desktop Host

### `src-tauri/src/lib.rs`

Rust Tauri app core.

- Exposes frontend commands: `run_tutor`, `click_screen_point`, `show_overlay`, `hide_overlay`, `show_command_bar`, `resize_command_window`, `resize_and_move_command_window`, `get_settings`, `save_settings`.
- Spawns `python/main.py` for screen-tutor requests.
- Sends `question`, `previous_question`, `progress`, and `conversation_history` over stdin.
- Watches stdout for `__BLINKY_CAPTURED__` and restores capture visibility immediately.
- Emits `blinky://guidance`, `blinky://open-command`, `blinky://global-click`, and `blinky://global-enter`.
- Uses Windows `SendInput` for `click_screen_point`, receiving physical screen coordinates from the frontend autopilot loop.
- Registers Ctrl+Shift+Enter and Ctrl+Shift+Space, with the active shortcut selected by `.env`.
- Starts the WebSocket server from `websocket.rs`.

### `src-tauri/src/websocket.rs`

Remote-control WebSocket server.

- Binds `0.0.0.0:9001`.
- Accepts raw power commands and JSON query messages.
- Starts/reuses a persistent `python -u python/agent_router.py` daemon.
- Streams daemon response lines back to the WebSocket client.
- Restarts the daemon once if it exits or its pipe breaks.

### `src-tauri/tauri.conf.json`

Defines the two main windows:

- `command`: `/command`, transparent, always-on-top, initially hidden.
- `overlay`: `/overlay`, transparent, click-through configured in Rust, initially hidden.

## 2. Frontend

### `frontend/src/main.tsx`

Route switch:

- `/command` -> `CommandBar`
- `/overlay` -> `Overlay`
- `/` -> `App`

### `frontend/src/CommandBar.tsx`

Primary command UI.

- Submits tutor requests through `runTutor()`.
- In globe/web mode, runs `runWebActionThenScreenGuidance()` and then `runAutopilotLoop()` for bounded safe clicks.
- Tracks progress, current guide step, completed targets/instructions, last query, and conversation history.
- Handles Sarvam microphone recording, transcription, TTS playback, and voice-first readback.
- Listens for `blinky://target-clicked` and `blinky://global-enter` to advance workflows.
- Emits `blinky://guidance` directly after a `runTutor` result and shows/hides overlay based on highlightable steps.
- Saves provider, shortcut, Groq key, and Sarvam key through Tauri settings commands.

### `frontend/src/App.tsx`

Fallback/default command route. It has prompt input, settings, and basic result display, but it does not include the richer continuation and voice workflow in `CommandBar.tsx`.

### `frontend/src/Overlay.tsx`

Transparent highlight renderer.

- Receives `TutorResult` via `blinky://guidance`.
- Uses `getHighlightSteps()` to render only the active matched target.
- Maps screenshot-space rectangles to CSS pixels.
- Handles Windows device-pixel-ratio and Linux overlay y-offset.
- Emits `blinky://target-clicked` when a global click lands in a highlighted frame.

### `frontend/src/lib/guidance.ts`

Pure step-state helpers.

- Filters displayable steps.
- Selects the current pending step.
- Selects highlightable steps.
- Decides whether highlight click should complete a step.
- Merges completed history with the current pending step.
- Decides whether the summary bubble should be visible.

### `frontend/src/lib/autopilot.ts`

Bounded observe-act loop for command-bar globe/web mode.

- Observes the current screen through a caller-provided `observe()`.
- Allows only matched click/open/select/choose/go-to style steps.
- Blocks typing, submit, install, enable, delete, purchase/payment, and login actions.
- Converts matched screenshot-space centers into physical screen coordinates using `screenshot.screen_width` and `screenshot.screen_height`.
- Stops on completion, unsafe/missing targets, unchanged repeated targets, or the max-attempt limit.

### `frontend/src/lib/webGuidance.ts`

Bridge between browser intelligence and screen guidance.

- Calls `runAgentQuery()` first for web tasks.
- Calls `runTutor()` after the browser action to read the visible screen.
- Falls back to the browser result if screen guidance fails.

### `frontend/src/lib/tauri.ts`

Typed wrappers around Tauri `invoke()` calls, including `clickScreenPoint()` for native autopilot clicks.

### `frontend/src/lib/tts.ts`

Sarvam payload helpers and error parsing.

## 3. Screen Tutor Python Worker

### `python/main.py`

Stdin/stdout screen-tutor orchestrator.

- Normalizes request payloads.
- Classifies screen vs chat requests.
- Handles continuation and conversation history.
- Runs the Web Intelligence Layer when `web_search_enabled` is true.
- In `agent_mode`, attempts direct computer-use actions first (`OPEN_APP`, `MEDIA_PLAYBACK`, `SYSTEM_SHORTCUT`) and falls back to screen mode on failed tool execution.
- Captures screen and prints `__BLINKY_CAPTURED__`.
- Resolves locator fast-path requests.
- Reads active app metadata, OCR items, and UIA items.
- Scales UIA coordinates into screenshot space.
- Merges and sorts visible items.
- Builds prompts, calls the selected AI provider, attaches matches, fills search fallbacks, and slices to one step.
- Returns both optimized screenshot dimensions and physical screen dimensions so frontend clicks can be scaled correctly.

### `python/computer_use/agent.py`

Regex-first routing helper for desktop agent mode.

- Routes app-launch commands (`open/launch/start <app>`) to `open_app_tool()`.
- Routes Spotify media requests (`play ... on/in spotify` or `play spotify ...`) to `play_spotify_track_tool()`.
- Routes contextual help-menu requests to `shortcut_tool("alt+h")` when VS Code-like context is detected.
- Avoids treating in-app actions like “open new tab” as app-launch requests.

### `python/computer_use/tools.py`

Windows-first direct action toolset used by agent mode.

- `open_app_tool()`: protocol -> known executable path -> `Get-StartApps` AppID -> safe process alias -> Windows Search fallback.
- `shortcut_tool()`: normalizes user shortcuts into pywinauto key syntax and sends them.
- `play_spotify_track_tool()`: resolves a Spotify track URI using SearXNG first, then DuckDuckGo HTML fallback, and opens it with `os.startfile("spotify:track:...")`.
- Returns typed `ToolResult` objects so callers can safely fall back when actions fail.

### `python/ai/prompt.py`

Prompt builders.

- `build_preflight_prompt()`: screen-vs-chat and continuation classifier.
- `build_chat_prompt()`: no-screen conversation response.
- `build_prompt()`: visual-context screen tutor prompt.
- Labels unlabeled UIA controls as `Visible Button 1`, `Visible Image 1`, etc. for vision-assisted matching.

### `python/ai/client.py`

Provider router for `ollama` and `groq`.

### `python/ai/ollama_client.py`

Local Ollama client using JSON output, `temperature: 0.1`, `num_predict: 350` for main guidance, and default timeout `35` seconds.

### `python/ai/groq_client.py`

Groq OpenAI-compatible client. Vision calls send the screenshot as a base64 JPEG data URL and request JSON-object output.

### `python/capture/screen.py`

Capture strategies and `Screenshot` dataclass.

- Windows: `dxcam`, falling back to PIL `ImageGrab`.
- Linux: portal/CLI helpers, `gnome-screenshot`, `maim`, `scrot`, then PIL fallback.
- Saves optimized JPEGs under `screenshots/`.
- Thumbnails captures to fit `1920x1080`.

### `python/ocr/extract.py`

OCR provider registry.

- Windows: WinRT OCR when available.
- Fallback/non-Windows: pytesseract if the binary and Python package are available.
- Final fallback: mock provider returning no OCR items.

### `python/utils/uia.py`

Windows UI Automation extraction through pywinauto. Uses `target_pid` to re-resolve a fresh COM window after capture/OCR delays.

### `python/utils/window.py`

Active window and overlay exclusion helpers. Supplies target PID locking and ignored overlay rectangles.

### `python/utils/matching.py`

Target matcher.

- `attach_matches()` attaches a `match` object to each step.
- `find_best_match_with_score()` returns diagnostics for locator fast path.
- Uses exact/partial/fuzzy text matching, confidence weighting, control bonuses, source penalties, and ambiguity counting.

## 4. Remote Agent Python

### `python/agent_router.py`

Line-oriented sidecar daemon for WebSocket queries.

- Tries the safe browser planner before registered/generated tools.
- Directly handles known open/search commands.
- Loads `python/tools/registry.json`.
- Routes to registered tools by LLM decision.
- Runs up to 3 tool calls concurrently.
- Checks sufficiency.
- Repairs common generated Playwright API mistakes, then audits, verifies, and registers tools when needed.
- Streams synthesized text chunks back to Rust.

### `python/browser_agent.py`

Safe JSON browser planner used before the slower generated-tool path.

- Classifies requests into `open_url`, `web_search`, or `site_search`.
- Rejects unsupported browser actions instead of inventing brittle scripts.
- Runs accepted plans through `BrowserController`.

### `python/browser_controller.py`

Persistent Playwright browser controller.

- Launches Chromium with `channel="msedge"` by default.
- Uses visible browser mode by default.
- Reuses the browser/context/page across requests when possible.

### `python/wil/`

SearXNG-backed Web Intelligence Layer.

- `pipeline.py`: coordinates planning, SearXNG retrieval, content acquisition, processing, and answer synthesis.
- `searxng_client.py`: queries local SearXNG JSON search at `http://localhost:8888`.
- `acquirer.py`, `http_fetcher.py`, `browser_engine.py`: fetch source pages through HTTP first, escalating to Playwright for thin/blocked pages.
- `processor.py`: cleans and selects relevant source text.
- `reasoner.py`: synthesizes the final answer with the configured AI provider, with fallback source summaries when synthesis is unavailable.

### `python/tools/registry.json`

Registry of known browser/data tools and their argument names.

### `python/utils/sufficiency_checker.py`

Determines whether a tool result is enough to answer the original query.

### `python/utils/generalizer.py`

Background generalization path for generated tools.

## 5. Mobile

### `mobile/App.tsx`

Expo remote controller UI. Saves PC host, connects over WebSocket, sends queries and power commands, and renders streaming agent status/results.

### `mobile/usePCWebSocket.ts`

WebSocket hook. Appends `:9001` when needed, tracks connection state, parses JSON messages, and exposes `sendCommand()` / `sendQuery()`.

### `mobile/AGENTS.md`

Project instruction: check the exact Expo versioned docs before editing mobile code.
