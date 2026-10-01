# Runtime flows

## Desktop startup

`common/src-tauri/src/main.rs` calls the library `run()` function. Startup then:

1. resolves the repository/resource root and loads `.env`,
2. builds the tray and command/overlay windows,
3. registers global events and shortcuts,
4. starts the WebSocket server and persistent agent daemon; development serves `ws://` and a release build serves pinned-identity `wss://` on port 9001,
5. starts `ui_observer.py` unless `BLINKY_DISABLE_UI_OBSERVER` is truthy,
6. starts the WhatsApp backend unless `BLINKY_DISABLE_WHATSAPP` is truthy,
7. starts the wake-word detector when its runtime/model are available, and
8. on Linux, attempts to make `ydotoold` available for input fallback.

The configured frontend routes are `/command` and `/overlay`. `main.tsx` also renders `App.tsx` for `/`, but `tauri.conf.json` does not currently define a main window. Both Ctrl+Shift+Enter and Ctrl+Shift+Space are registered as toggles, regardless of the saved `BLINKY_SHORTCUT`; Ctrl+Space and Super/Win+Space participate in push-to-talk behavior.

## Standard tutor request

```text
CommandBar submit
  -> Tauri run_tutor
  -> hide/exclude Blinky windows from capture
  -> spawn common/python/main.py
  -> JSON request on stdin
  -> classify intent / collect app state
  -> capture + OCR + accessibility map when needed
  -> model or deterministic path produces TutorResult
  -> status/chunk events and final JSON
  -> React renders guidance and overlay
```

Rust restores the hidden/capture-excluded windows when Python emits `__BLINKY_CAPTURED__`; otherwise it restores them when the worker finishes. Do not turn that marker into ordinary logging.

`main.py` first checks deterministic and low-cost paths. The effective order is:

1. explicit web-search mode,
2. agent-mode direct tools,
3. local locator/progress fast paths or AI preflight,
4. routed web search, AiCut, WhatsApp, computer-use/open-app/media/system shortcuts,
5. screen explanation/locator,
6. full capture, UI-map, prompt, provider, matching, and one-step guidance.

The comment near `main.py::run` says agent mode does not capture, but current agent behavior can invoke the Linux computer-use loop or a procedural plan that captures and grounds the next screen step.

## Screen observation and grounding

1. Active app/window is resolved, optionally locked to a target PID.
2. Capture uses PIL ImageGrab then DXCam on Windows; Linux selects an X11, grim, portal, GNOME Screenshot, or Spectacle strategy.
3. The image is normalized to a maximum 1920x1080 JPEG at quality 75 for the normal capture path.
4. OCR mode is selected. Default Windows order is WinRT OCR then fallback; Linux uses Tesseract. `BLINKY_SCREENSHOT_MODE=omniparser` selects remote/local OmniParser.
5. Accessibility elements come from Windows UIA or Linux AT-SPI where available.
6. Blinky windows and known overlay/system regions are filtered.
7. Accessibility rectangles are calibrated to screenshot dimensions, merged with OCR, deduplicated, and assigned stable refs.
8. The matcher prefers `target_ref`, then scores exact/fuzzy text plus control/input context and rejects weak or ambiguous matches.
9. The overlay converts screenshot coordinates to CSS coordinates using screenshot/screen dimensions, DPR, window position, and platform offsets.

The UI-map cache lives under `python/cache/ui_maps` relative to the process working directory. Captures live under `screenshots/`; parsed/debug images may live under `screenshots_parsed/` or `tmp/`.

## React observe/act loop

`CommandBar.tsx` owns the user-facing loop. In agent mode it requests fresh guidance, executes at most one action for a single-step result or up to five iterations for a multi-step flow, and gives an action up to two retries. Failed refs/targets are fed into the next request for self-healing.

Supported frontend actions are:

- click at a matched point,
- scroll at a matched point,
- extract text from an instruction and type it, optionally pressing Enter.

The safety classifier allows instructions containing click/open/select/choose/go to/type/enter/search/submit/scroll. It blocks install/enable/delete/remove/buy/purchase/pay/sign-in/login. A usable match/confidence is still required. Normal tutor mode can also auto-click a single click-like matched instruction.

Stop clears the frontend loop and audio state. It is not a general cross-process cancellation protocol.

## Linux autonomous computer-use loop

`run_computer_use_loop` is a separate, Linux-only tool loop:

1. load app inventory and approved recipes from `.brain/ARTIFACTS/recipes`,
2. build a system prompt and initial visual plan,
3. ask the text model for one tool call,
4. enforce call limits and loop/repetition checks,
5. execute through `computer_use/tools.py` and the Linux backend,
6. capture and OCR the post-action screen,
7. verify the action with vision,
8. diagnose/recover/re-plan on failure, and
9. on success, stage a reusable recipe and emit a desktop approval prompt.

Recipes have a registry and per-recipe JSON. Rust `confirm_recipe_save` either retains the staged recipe or removes it. Vision metrics are JSONL under `.brain/logs/vision`.

## Procedural screen plan

When a request needs procedural knowledge, `step_planner.py` checks built-in templates, can search through SearXNG, and asks the text provider for structured steps. `text_grounder.py` grounds the current step against stable refs and heuristics, with a text-model disambiguation pass when needed. This is distinct from the autonomous Linux loop: it returns screen guidance for React to execute.

## Web information layer

Explicit web mode and classified web-search intents run `WILPipeline`:

1. plan query variants,
2. test the configured local SearXNG and known public fallbacks,
3. retrieve results,
4. acquire the top three pages using HTTP and browser fallback,
5. normalize and process page content,
6. reason with the active text provider, and
7. append source links.

If search is unavailable, the pipeline can fall back to a model-only answer and should surface that limitation.

## Persistent agent daemon and browser tools

The Tauri WebSocket server starts `agent_router.py` and exchanges one JSON object per line. The router attempts deterministic browser/open-URL/direct tools before general model planning. `browser_agent.py` only accepts `open_url`, `web_search`, and `site_search`; `browser_controller.py` runs a visible persistent Playwright browser by default, preferring Microsoft Edge.

The generalization path can ask the model to produce Python tool code, write it under `common/python/tools/`, verify it, and mutate `tools/registry.json`. This is source mutation at runtime/development time. Review generated code, network targets, arguments, and registry diffs before retaining it.

## Mobile remote

`common/mobile/usePCWebSocket.ts` connects directly to the desktop at port 9001. Development uses the existing React Native `ws://` client. Release uses the local Expo module at `common/mobile/modules/blinky-secure-socket/`, which performs native WSS certificate pinning and sends JSON auth. `App.tsx` stores the desktop IP in AsyncStorage; release token and certificate pin are stored through Android Keystore/iOS Keychain, while development keeps the legacy AsyncStorage fallback.

Release requires both `BLINKY_REMOTE_TOKEN` and the desktop certificate pin. The hook waits for `auth_result` with strict boolean `ok: true` before reporting connected or sending commands. Its connection deadline includes authentication; rejection, timeout, and premature-close errors survive cleanup. Stale native completions cannot overwrite a newer connection. Release discovery probes with native WSS; development discovery probes plain WS. Queries receive streamed desktop status/results. The UI supports device control, text queries, and Sarvam voice. Power actions receive mobile-side confirmation; the desktop protocol itself has no matching confirmation handshake. Mobile stop only stops local recording/visual state.

Mobile requests the Sarvam API key from the desktop and then calls Sarvam directly. Current desktop CommandBar also calls Sarvam directly through HTTPS for STT/TTS; its normal speech path does not use the Rust `/sarvam-stt` and `/sarvam-tts` proxies.

### Mobile file transfer

In the Chat composer, the attachment menu's **Send files to PC** action opens `FileTransferPanel`. Its separate **File** action attaches a file to the chat query. The panel accepts a mixed batch (such as PDF, PNG, video, and audio) and an optional absolute PC folder path; blank means `Downloads/Blinky`. The native Expo module reads selected documents in bounded buffers to calculate SHA-256 and stream file chunks; JavaScript never loads a whole transfer file into memory. Each `file_offer` carries the destination path and file metadata. `file_offer`, `file_resume`, `file_cancel`, and `file_edit` are JSON control messages on the WebSocket. The separate Rust port-9002 HTTP(S) listener accepts 16 MiB maximum upload chunks with explicit offsets and serves output ranges. A final upload moves from `Downloads/Blinky/.staging` to the validated destination only after the offered size and hash match. Available disk space and the configurable `BLINKY_FILE_TRANSFER_MAX_BYTES` cap are checked before staging.

The mobile Files screen can also download a PC file through `fs_read_file` over the authenticated WebSocket. Its per-file ceiling uses the same configurable limit (20 GiB by default). This older path reads the complete file and base64-encodes it in memory before sending; the 20 GiB value is a rejection ceiling, not a guarantee that a device can practically buffer a file that large.

The server keeps the offset, digest state, destination, and temporary bearer capability in memory for up to 24 hours. Wi-Fi interruption can resume while both app and PC process stay alive; restarting either loses the session. A blank AiCut instruction uploads every file without editing, even for multiple videos. An explicit merge, trim, audio, or captions instruction starts the dedicated structured worker with only uploaded paths; selection alone never adds an operation. AiCut supports video/audio edits, while PDFs and images remain uploaded files. Its result is saved in the selected PC folder, downloaded into app storage with Range requests, SHA-256 verified, and shared through the platform share sheet. Custom development/release builds are required on Android and iOS; Expo Go does not contain this local native module. App transport config permits cleartext only in development; release uses the shared WSS/HTTPS P-256 pin.

## Speech and wake word

- `sarvamStream.ts` provides optional desktop STT/TTS classes through local WebSocket proxies. In release they use the native pinned-WSS bridge; development uses browser WebSocket. CommandBar holds typed refs but does not instantiate these classes. Native setup cancellation and queued STT audio are covered by mocked bridge tests, not live provider tests.
- `adaptiveTransport.ts` probes an HTTP/3/WebTransport gateway and falls back to a direct Sarvam WebSocket. `CommandBar` initializes it when a key exists, but the normal STT/TTS stream classes remain separate.
- `tts.ts` contains older/non-streaming TTS utilities used by tests and some fallback behavior.
- The wake-word Python process loads `python/hey_blinky.onnx`, listens to the microphone, and signals Rust. React pauses/resumes wake listening around active capture/speech.

## WhatsApp

Tauri starts `common/whatsapp_backend/server.js`. It normally binds loopback on port 3000 and tries higher ports when occupied. The React client probes 3000–3005.

The server owns one effective session, `blinky-default-session`, using whatsapp-web.js `LocalAuth`. Its REST/Socket.IO surface provides QR/status, chat list/read, summaries, settings, logout, and diagnostics. `WaUserSession.js` handles Chromium/Edge launch, connection watchdog/restart, unread sync, Groq summarization, summary memory, media vision, message commands, and optional ntfy notifications.

The source frontend for this service is not present; only built files under `common/whatsapp_backend/frontend/` are tracked. Regenerate them from their upstream source rather than editing minified assets.

## AiCut

`main.py` recognizes editing intents deterministically through `common/python/tools/aicut_tool.py`. That adapter resolves referenced/Explorer files and dispatches trim, music, merge, subtitles, transcription, media inspection, or combined pipelines.

The C++17 `AIVideoEditor` CLI builds FFmpeg command lines for trim, add-music, and merge. `common/aicut/aicut_mcp.py` exposes a JSON-lines/stdio MCP-style interface and additional Python operations. Subtitle preset generation/rendering lives in `common/python/subtitles/`. FFmpeg/ffprobe are runtime prerequisites; faster-whisper models download/cache separately.

## Direct remote commands

The desktop server handles power off, restart, sleep, volume up/down, mute, lock, screenshot, and Sarvam-key retrieval without invoking the Python assistant. Platform Rust modules translate those requests to Windows APIs/commands or Linux system utilities. These commands share the WebSocket authentication boundary described in [SECURITY-AND-RISKS.md](SECURITY-AND-RISKS.md).
