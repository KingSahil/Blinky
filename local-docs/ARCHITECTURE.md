# Architecture

## System context

```text
                           external model/search/speech APIs
                         Groq / Ollama / custom / Sarvam / SearXNG
                                          ^
                                          |
Expo mobile -- native pinned WSS (release) / WS (dev) :9001 -- Rust/Tauri host -- local WhatsApp service :3000+
     | native pinned HTTPS (release) / HTTP (dev) :9002          |   ^
                                    JSON/stdin |   | events/commands
                                              v   |
                                      Python worker/daemon
                                      |       |        |
                                 screen/UI   tools   web/browser
                                      |
                         Windows adapters / Linux backend
                                      |
                              desktop OS and apps

React command bar + overlay run inside Tauri and communicate with Rust through Tauri invoke/events.
AiCut is invoked from Python and shells out to its C++ executable and/or FFmpeg tooling.
```

## Process boundaries and ownership

| Boundary | Primary source | Owns | Does not own |
|---|---|---|---|
| Tauri host | `common/src-tauri/src/lib.rs` | app lifecycle, windows, tray, shortcuts, native input commands, child processes, settings, wake-word process | intent classification or screen reasoning |
| LAN/daemon bridge | `common/src-tauri/src/websocket.rs` | WebSocket protocol, mobile commands, Sarvam proxies, persistent `agent_router.py` daemon | UI presentation |
| Desktop UI | `common/frontend/src/` | command/overlay rendering, user modes, streaming status, direct HTTPS Sarvam TTS/STT, bounded autopilot execution | LAN server ownership |
| Python orchestrator | `common/python/main.py` | intent preflight, fast-path routing, capture/OCR/UI-map pipeline, tutor result contract | native window lifecycle |
| Agent daemon | `common/python/agent_router.py` | line-delimited query service, deterministic/browser/tool routing, generated tool registry | desktop WebSocket transport |
| Computer-use engine | `common/python/computer_use/` | Linux agent loop, planning, grounding, action tools, verification, recovery, recipes | React safety/UI state |
| Web information layer | `common/python/wil/` | query planning, SearXNG retrieval, acquisition, processing, reasoning, sources | OS automation |
| OS adapters | `windows/python/`, `linux/python/backend/`, platform Rust files | capture, OCR/accessibility, windows, input, power/media commands | product routing policy |
| Mobile remote | `common/mobile/` | discovery, release native pinned-WSS/HTTPS and Keystore-or-Keychain connection, development WS/HTTP connection, file picker, streaming transfer, query/voice UX | desktop execution and process-restart recovery |
| WhatsApp service | `common/whatsapp_backend/` | WhatsApp Web session, QR/status/chats/summaries, Socket.IO UI, ntfy | core tutor protocol |
| AiCut | `common/aicut/`, `common/python/tools/aicut_tool.py` | deterministic edit intent, FFmpeg operations, subtitles/transcription/media inspection | general desktop automation |

## Deployment units

- **Desktop dev process:** Vite plus Tauri, launched through `scripts/dev.ts` or `bun run tauri:dev`.
- **Desktop release process:** the Tauri bundle built by `bun run build:release`; Rust serves WSS on port 9001 using its persisted self-signed P-256 identity. Desktop queries use Tauri IPC; current speech uses direct provider HTTPS. A native WSS speech bridge is available but not instantiated by CommandBar.
- **File transfer listener:** the Rust host binds port 9002 on LAN interfaces. Development uses HTTP; release wraps the listener in TLS with the same persisted P-256 identity as WSS. Authenticated WebSocket control creates short-lived transfer capabilities; HTTP(S) carries bounded file chunks.
- **Python one-shot worker:** `common/python/main.py`, spawned per `run_tutor` request. Input is one JSON document on stdin; output is line-oriented status/chunk records plus a final result.
- **Python persistent daemon:** `common/python/agent_router.py`, owned by the WebSocket server. Each input and output line is JSON keyed by `requestId`; Rust restarts the daemon once after failure.
- **UI observer:** `common/python/ui_observer.py`, an optional child process that refreshes app-context observations.
- **Wake-word detector:** root `python/wake_word.py`, controlled with `PAUSE`/`RESUME` stdin and emitting `WAKE_WORD_DETECTED`.
- **WhatsApp backend:** local Express/Socket.IO process, normally spawned by Tauri and bound to loopback on the first available port from 3000 upward.
- **SearXNG:** Docker service published at `127.0.0.1:8888` from container port 8080.
- **Expo:** Metro at 8081; Android tooling and LAN discovery are orchestrated by `scripts/dev.ts`.

## Core data contracts

### Tutor request

React calls Tauri `run_tutor` with:

- `question`
- optional `previous_question`
- optional progress (`completed_targets`, `completed_instructions`, failed targets/refs)
- optional conversation history
- `web_search_enabled`
- `agent_mode`

Rust serializes the request to `common/python/main.py`. The Python result is represented by `TutorResult` in `common/frontend/src/lib/types.ts` and matching Rust structs in `lib.rs`. `common/shared/clicky-result.schema.json` is a legacy/basic schema, is not wired as runtime validation, and omits newer fields.

### Tutor result

Stable core fields are `summary`, `steps`, `active_app`, `ocr`, optional `screenshot`, `elapsed_ms`, and `warnings`. Newer optional fields include provider, continuation/app context, direct `agent_action`, and computer-use/fallback flags. Steps may carry a stable `target_ref`, human text target, and matched screen element.

### Screen element

The merged UI map combines OCR with Windows UI Automation or Linux AT-SPI data. Elements may include text, rectangle, confidence, control metadata, source, click/input flags, stable `ref`, and match diagnostics. Refs are preserved across compatible UI-map cache observations and are preferred over fuzzy text.

### WebSocket protocol

Development keeps the existing plain `ws://` behavior. Release uses `wss://` on the same port and rejects non-loopback clients until they send JSON auth. The server accepts JSON messages and legacy text commands after authentication. Important message families are:

- development auth (`auth:<token>` or query token)
- release auth (`{"type":"auth","token":"..."}`) with an explicit `{"type":"auth_result","ok":true|false}` response
- agent query (`query:<requestId>:<query>` or JSON request)
- streamed status/result responses keyed by request ID
- direct device commands (power, restart, sleep, volume, mute, lock, screenshot, Sarvam-key request)
- `/sarvam-stt` and `/sarvam-tts` proxy paths

The optional release desktop speech stream classes use the Tauri native bridge (`secure_socket_connect`, `secure_socket_send`, and `secure_socket_close`) so a private self-signed certificate is not delegated to WebView trust. Current CommandBar does not instantiate those classes. The mobile native module uses the gateway with a user-provided `sha256/<SPKI>` pin.

### File transfer protocol

`common/mobile/FileTransferPanel.tsx` selects mixed file batches and hashes each file in the native module, then sends a `file_offer` per file over the port-9001 WebSocket. The offer carries an optional absolute PC `destinationPath`; a blank value defaults to `Downloads/Blinky`. Rust validates the filename, destination folder, size, free space, and SHA-256 metadata; it returns a random transfer ID and per-transfer 256-bit bearer capability, reused for chunk uploads and resume requests. The native mobile bridge streams up to 16 MiB per request to `POST /upload/{transferId}` on port 9002 with an `Upload-Offset`. Rust stages under `Downloads/Blinky/.staging`, checks the final size and SHA-256, then finalizes in the selected folder with a collision-safe name, including across filesystems.

While the Blinky app and desktop process remain alive, `file_resume` reports the server's acknowledged offset after a Wi-Fi interruption. The transfer map and temporary capability are in memory, so restarting either process does not resume a transfer. The default cap is 20 GiB and `BLINKY_FILE_TRANSFER_MAX_BYTES` overrides it in bytes. Release HTTP requests use HTTPS pinned to the same desktop identity as WSS; native code rejects unpinned HTTPS and pinned HTTP.

Only an explicit AiCut instruction sends a separate `file_edit` control request after the full batch uploads. Rust starts `common/python/file_transfer_aicut.py` with a structured JSON request. That worker supplies only uploaded paths and an empty Explorer context to the deterministic AiCut resolver, disables implicit operations inferred from multiple selected files, and restricts output to the chosen destination folder. PDF and image files transfer but are not AiCut edit inputs. The phone downloads the result by HTTP Range requests, verifies SHA-256, stores it under app files, and offers the OS share sheet. Expo Go cannot load the project-local native file streaming module; install a custom development or release build.

The listener is not merely local IPC: it binds all interfaces. See [SECURITY-AND-RISKS.md](SECURITY-AND-RISKS.md).

## Architectural invariants

1. **Rust is the privileged shell.** React invokes native work; Python returns plans/results; platform-specific privilege stays in Rust or platform adapters.
2. **Python protocols are stdout-sensitive.** Human/debug logs belong on stderr or log files. JSON control messages and `__BLINKY_CAPTURED__` must remain machine-readable.
3. **Observe before acting.** Tutor matching and the Linux computer-use loop ground actions against current UI evidence; verification observes the post-action screen.
4. **One UI action at a time.** Python normally slices guidance to one step and the React autopilot loops through fresh observations. This limits stale-coordinate cascades.
5. **Coordinates retain their space.** Captured image size, physical screen size, active-window bounds, scale factor, and overlay offset are carried through conversions.
6. **Platform branching stays behind adapters.** `linux/python/backend/abc.py` defines the computer-use contract; Windows equivalents provide UIA/capture/tools. Generic routing imports through these seams.
7. **Local persistence is explicit.** Desktop WSS identity files live under the OS app-data directory; release mobile connection credentials live in Android Keystore/iOS Keychain; development connection values remain in AsyncStorage for Expo Go compatibility. Other secrets live in `.env`; learned recipes and vision logs in `.brain`; screen/UI caches and WhatsApp session data are runtime artifacts and ignored by Git.
8. **Generated automation requires review boundaries.** Generated browser tools mutate the registry/source tree; learned recipes are staged and require explicit desktop approval before retention.

## Coupling hotspots

Codebase Memory identifies the largest orchestration/coupling points as:

- `common/python/main.py::run`
- `common/python/agent_router.py::handle_request`
- `common/python/computer_use/agent.py::try_run_agent_action`
- `common/python/computer_use/loop.py::run_computer_use_loop`
- `common/python/tools/aicut_tool.py::resolve_aicut_request`
- `common/src-tauri/src/lib.rs::run`
- `common/frontend/src/CommandBar.tsx`

Changes here should be split into helper-level edits where possible and validated against all adjacent protocols.

## Deliberate asymmetries

- The full autonomous computer-use loop is Linux-specific. Windows primarily uses direct tools plus the React observe/act guidance loop.
- Current desktop speech and mobile speech call Sarvam directly; optional desktop streaming classes provide local Rust WebSocket proxy access but are not the active CommandBar speech path.
- Desktop direct remote commands execute without a confirmation protocol; mobile presents confirmations for destructive power actions only in its UI.
- Runtime source supports Linux, but Tauri bundle configuration currently lists only the Windows NSIS target.
