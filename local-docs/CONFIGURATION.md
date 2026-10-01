# Configuration and runtime state

Configuration is loaded primarily from the repository-root `.env`. Rust settings reads/writes that file in plaintext. Python also loads it, and the WhatsApp service overlays its own settings. Never commit real secrets.

## Canonical keys

### Core AI

| Key | Purpose | Current source default/notes |
|---|---|---|
| `BLINKY_AI_PROVIDER` | `ollama`, `groq`, `deepseek`, `mimo`, or `custom` | Provider resolver uses explicit value; when absent it prefers configured Groq, then MiMo, then DeepSeek, otherwise Ollama. Some subsystems independently default to Ollama. |
| `BLINKY_OLLAMA_URL` | Ollama generate endpoint | `http://localhost:11434/api/generate` |
| `BLINKY_OLLAMA_MODEL` | local model | `gemma4:e4b` |
| `BLINKY_OLLAMA_TIMEOUT` | Ollama seconds | 35 |
| `GROQ_API_KEY` | Groq credential | required for Groq |
| `BLINKY_GROQ_URL` | Groq-compatible chat endpoint | `https://api.groq.com/openai/v1/chat/completions` |
| `BLINKY_GROQ_MODEL` | Groq text model | provider client: `qwen/qwen3.8-27b`; WIL/agent-router fallback code still uses `openai/gpt-oss-120b` |
| `BLINKY_GROQ_VISION_MODEL` | Groq vision model | falls back to `qwen/qwen3.8-27b`; GPT-OSS values are rejected for vision |
| `BLINKY_GROQ_TIMEOUT` | request timeout seconds | 90 for text path |
| `BLINKY_GROQ_MAX_RETRY_WAIT` | rate-limit wait ceiling | 35 seconds |
| `BLINKY_GROQ_IMAGE_MAX_DIM` | uploaded image max dimension | 768 |
| `DEEPSEEK_API_KEY` | DeepSeek-compatible credential | required for DeepSeek |
| `BLINKY_DEEPSEEK_URL` | DeepSeek-compatible base | `https://opencode.ai/zen/v1` |
| `BLINKY_DEEPSEEK_MODEL` | DeepSeek model | `deepseek-v4-flash-free` |
| `MIMO_API_KEY` | MiMo-compatible credential | required for MiMo |
| `BLINKY_MIMO_URL` | MiMo-compatible base | `https://opencode.ai/zen/v1` |
| `BLINKY_MIMO_MODEL` | MiMo model | `mimo-v2.5-free` |
| `CUSTOM_API_KEY` | custom OpenAI-compatible credential | may be empty only if endpoint allows it |
| `BLINKY_CUSTOM_URL` | custom base URL | `https://opencode.ai/zen/v1` |
| `BLINKY_CUSTOM_MODEL` | custom model | `minimax-m3` |

Model defaults are deliberately reported per source because they are not fully unified. Do not “clean up” a mismatch without checking WIL, agent daemon, tutor provider, WhatsApp, setup docs, and tests.

### Desktop, capture, and services

| Key | Purpose | Default/behavior |
|---|---|---|
| `BLINKY_SHORTCUT` | saved UI choice | created as `Space`; Rust fallback read uses `Enter`, but both global toggles are currently registered |
| `BLINKY_REMOTE_TOKEN` | LAN WebSocket shared secret | empty preserves legacy development LAN behavior, including file offers; release mobile file transfer requires a configured token, so set a strong value |
| `BLINKY_TRANSPORT_MODE` | Rust transport build mode | `development` by default; `release` enables WSS and fail-closed remote auth |
| `BLINKY_FILE_TRANSFER_MAX_BYTES` | Maximum size of one mobile transfer in either direction | 20 GiB by default (`21474836480` bytes); applies to mobile uploads and PC-to-mobile file downloads; invalid or non-positive values use the default |
| `BLINKY_DISABLE_UI_OBSERVER` | skip observer child | false/unset starts observer |
| `BLINKY_UI_OBSERVER_INTERVAL` | observer interval | read by observer/startup; use seconds |
| `BLINKY_UI_OBSERVER_PARENT_PID` | observer parent liveness | normally set by Rust, not by users |
| `BLINKY_DISABLE_WHATSAPP` | skip WhatsApp child | false/unset starts service |
| `BLINKY_SCREENSHOT_MODE` | `ocr` or `omniparser` | `ocr` |
| `BLINKY_OMNIPARSER_API_URL` | remote OmniParser endpoint/model reference | empty uses local attempt when OmniParser mode is selected |
| `BLINKY_OMNIPARSER_MODEL_DIR` | local model directory | `weights/omniparser` |
| `BLINKY_PROMPTS_CONFIG` | alternate agent YAML | `common/python/prompts/agent.yaml` resolved from source |
| `BLINKY_SEARXNG_URL` | preferred search endpoint | `http://127.0.0.1:8888` |
| `BLINKY_BROWSER_CHANNEL` | Playwright channel | `msedge` |
| `BLINKY_BROWSER_HEADLESS` | browser visibility | false by default |

### Speech/frontend build variables

| Key | Purpose | Default |
|---|---|---|
| `SARVAM_API_KEY` | Sarvam STT/TTS credential | none |
| `VITE_SARVAM_GATEWAY_STT_URL` | desktop STT proxy | `ws://127.0.0.1:9001/sarvam-stt` |
| `VITE_SARVAM_GATEWAY_TTS_URL` | desktop TTS proxy | `ws://127.0.0.1:9001/sarvam-tts` |
| `VITE_BLINKY_TRANSPORT_MODE` | frontend transport build mode | `development`; `release` selects the native Tauri WSS speech bridge |
| `VITE_SARVAM_GATEWAY_WT_URL` | adaptive WebTransport gateway | `wt://gateway.blinky.internal/sarvam-stream` |

Vite values are build-time frontend variables. The adaptive fallback constructs a direct Sarvam WebSocket containing the API key; normal desktop stream classes use the local proxies.

### WhatsApp service

| Key | Purpose | Notes |
|---|---|---|
| `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_VISION_MODEL` | summarization and media vision | service/user settings may override; text default is `openai/gpt-oss-120b` |
| `ALLOWED_ORIGINS` | additional CORS origins | defaults already include local/Tauri origins |
| `PORT` / service port setting | preferred HTTP port | source starts at 3000 and increments on conflict |
| `PUPPETEER_EXECUTABLE_PATH` | Edge/Chrome executable | auto-detected when absent |
| `NTFY_ENABLED` | enable notifications | only exact `true` enables |
| `NTFY_TOPIC`, `NTFY_TITLE`, `NTFY_PRIORITY` | notification target/metadata | persisted user settings can override |
| `DEFAULT_MESSAGE_LIMIT` | summary message limit | editable service setting |
| `ALLOW_PUBLIC_COMMANDS` | fallback message-command policy | normal group/direct author checks are already broad; do not rely on this as a strict allowlist |
| `ALLOWED_COMMAND_PHONES` | comma-separated phone allowlist | consulted only in the fallback public-command branch |
| `HOST` | HTTP bind host | `127.0.0.1`; setting `0.0.0.0` exposes the service |
| `SHOW_TERMINAL_QR` | print login QR in terminal | false |
| `WWEBJS_AUTH_DIR` | whatsapp-web.js LocalAuth directory | repository-root `.wwebjs_auth` |

The WhatsApp settings API persists allowed keys under ignored runtime data. Masked values use `***` and are not overwritten when round-tripped.

Advanced WhatsApp environment-only tunables read through `getSetting` are `AUTO_SUMMARY_THRESHOLD` (100), `GENERAL_CONTEXT_MESSAGE_LIMIT` (30), `GENERAL_PERSISTENT_CONTEXT_TURNS` (12), `GENERAL_PERSISTENT_MEMORY_TURNS` (60), `MAX_STORED_SUMMARIES_PER_CHAT` (10), `ENABLE_MEDIA_ANALYSIS` (true), `MEDIA_VISION_MAX_BYTES` (3,000,000), `MAX_MEDIA_ANALYSIS_PER_SUMMARY` (12), `SUMMARY_CONTEXT_EXTRA` (30), `SUMMARY_FETCH_CACHE_TTL_MS` (120,000), `SUMMARY_TIME_WINDOW_FETCH_LIMIT` (500), and `SUMMARY_TIME_WINDOW_MAX_MESSAGES` (300). They are not accepted by the current settings-save allowlist.

### Setup/process-only variables

`SystemRoot`, `LOCALAPPDATA`, `PUPPETEER_SKIP_DOWNLOAD`, `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD`, desktop/session variables (`XDG_CURRENT_DESKTOP`, `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY`, `DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`), and Android/ADB variables are consumed by setup or platform tooling. They are environment prerequisites, not product settings.

`__BLINKY_CAPTURED__` is a protocol marker, not an environment key.

## Ports and addresses

| Port | Owner | Bind/exposure |
|---|---|---|
| 5173 | Vite dev server | local dev frontend |
| 8081 | Expo Metro | local/LAN development |
| 8888 | Docker SearXNG | host-published from container 8080 |
| 9001 | Rust WebSocket/Sarvam gateway | `0.0.0.0`, LAN-visible; `ws://` in development and `wss://` in release |
| 9002 | Rust mobile file transfer | `0.0.0.0`, LAN-visible; `http://` in development and HTTPS pinned to the same P-256 identity in release |
| 9003 | Antigravity hook bridge | `127.0.0.1`, loopback-only HTTP |
| 3000–3005 | WhatsApp backend discovery range | backend defaults to loopback and advances if occupied |
| 11434 | Ollama | standard local endpoint, not started by Blinky runtime |

## Persistent and generated state

| Location | Contents | Git |
|---|---|---|
| `.env` | plaintext provider/service secrets and settings | ignored |
| `.brain/ARTIFACTS/recipes/` | learned/staged workflow JSON and registry | ignored |
| `.brain/logs/vision/` | computer-use vision metrics JSONL | ignored |
| `python/cache/ui_maps/` | UI-map snapshots/ref continuity | ignored by root cache patterns |
| `screenshots/`, `screenshots_parsed/`, `tmp/` | captures, annotated images, debug/log files | ignored |
| `common/python/app_context/*.md` | per-app context/observations | tracked in this repository; runtime may enrich/create entries |
| `common/python/tools/registry.json`, generated tool scripts | executable tool registry/source | tracked; review diffs |
| repository-root `data/`, `.wwebjs_auth`, `.wwebjs_cache` | sessions, settings, summary memory, browser auth/cache | ignored |
| browser profiles / Playwright browsers | persistent browser state/binaries | local caches |
| Hugging Face/faster-whisper caches | transcription models | ignored/local |
| `common/python_runtime/Python313` | bundled Windows Python runtime | ignored; build prerequisite |
| `Downloads/Blinky/` | default destination for files received from mobile; temporary upload chunks always live under `.staging/` | user files, outside the repository |
| user-selected absolute PC folder | optional destination for a transfer batch and its AiCut output; must already exist and be writable | user files, outside the repository |
| app-private `BlinkyTransfers/` | edited-file download staging and completed shared copy | native mobile storage; not available to Expo Go |
| OS app-data `tls/identity-key.pem` and `tls/identity-cert.pem` | persisted release WSS server identity | generated once by Rust; do not delete unless intentionally rotating the mobile pin |

## Known configuration drift

- `.env_example` is the least-bad minimal template but does not list all supported keys.
- `common/.envexample` is malformed/stale and includes old `CLICKY_*` names; do not copy it.
- Root Rust/settings defaults, Python provider defaults, WIL/agent defaults, and setup-script examples are not fully unified.
- `common/searxng/settings.yml` contains the placeholder `blinky_secret_key_change_me`; replace it if the service is exposed beyond local development.
- The mobile subtree instruction references Expo 56 while its package currently pins Expo 57.
