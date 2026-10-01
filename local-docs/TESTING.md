# Testing and validation

## Validation matrix

| Area | Command | What it covers |
|---|---|---|
| Frontend typecheck | `bun run typecheck` | TypeScript compile contract for `common/frontend` |
| Frontend unit tests | `bun test common/frontend/tests` | Bun executes frontend tests directly, including mocked native speech lifecycle tests; no root convenience `test` script |
| Mobile unit tests | `bun test common/mobile/tests` | Mobile connection state, file transfer entry point, and destination/edit offer contract |
| Python syntax | `python -m compileall -q common/python linux/python windows/python python common/aicut/aicut_mcp.py` | parse/byte-compile all Python source |
| Python unit/integration | `python -m pytest common/python/tests -q` | 30 modules across routing, UI, computer use, WIL, tools, and providers |
| Rust/Tauri | `cargo test --locked --manifest-path common/src-tauri/Cargo.toml` | Rust unit tests and Tauri compile/build contract |
| AiCut native | `cmake -S common/aicut -B <build>; cmake --build <build>; ctest --test-dir <build> --output-on-failure` | CLI parser and trim/music/merge engine tests |
| Wake word | `python python/test_wake_word.py` | manual dependencies/audio/model/live detection; requires microphone and model runtime |
| Linux diagnostics | `bun run linux:check:ollama`, `bun run linux:check:groq`, `bun run linux:check:computer-use` | environment/service checks; last command targets the external package doctor |

Use the Python executable from the configured project environment. The Windows production requirements intentionally omit pytest, so install development test dependencies into `.venv`, not the pruned bundled runtime.

## Review validation on 2026-08-30

The documentation review ran these checks from the repository root:

- Python compileall: **passed** for core, Linux, Windows, root wake word, and AiCut MCP source.
- AiCut CMake build: **passed** with GNU C++ 16.2.1 in a temporary build directory.
- AiCut CTest: **4/4 passed** (`TrimEngineTests`, `CommandLineParserTests`, `MusicMergeEngineTests`, `MergeEngineTests`).
- Rust `cargo test --locked`: **blocked during Tauri build**, because configured resource `common/python_runtime/Python313` is absent. Dependencies compiled up to the application build script; no Rust test result should be inferred.
- Python pytest: **not run**, because the available Python 3.14 environment has no pytest and no project `.venv` is present.
- Frontend typecheck/tests: **not run**, because Bun and `node_modules` are absent. The unit-test runner also needs to be added to project configuration.

The Rust attempt created only ignored `common/src-tauri/target` output. AiCut was built in `/tmp`.

## Mobile transfer validation on 2026-09-28

- The transfer entry and offer tests passed (4/4), including a run from `common/mobile`, and `bunx tsc --noEmit -p common/mobile/tsconfig.json` passed.
- The AiCut resolver and transfer intent suite passed with the Linux-incompatible `test_run_trim_execution` case excluded (50 passed, 1 deselected). That excluded case tries to execute Windows `common/aicut/aicut.cmd` and fails with permission denied on Linux.
- The full mobile unit suite had one reconnect timer assertion failure in `usePCWebSocket.test.ts` (14 passed, 1 failed); the transfer-specific tests passed.
- `/usr/bin/rustfmt --check --edition 2021 common/src-tauri/src/file_transfer.rs` and `git diff --check` passed. The initial targeted Rust test was blocked by the absent `common/python_runtime/Python313` bundle. Setting `TAURI_CONFIG='{"bundle":{"resources":[]}}'` bypassed that resource and exposed an existing Linux compile error: `platform_impl::click_element_impl` is not exported by the Linux platform module. The transfer tests still could not run.

## Required checks by change type

For the dated September WSS review results, native build evidence, and remaining device gates, see [WSS-RELEASE.md](WSS-RELEASE.md). Run frontend and mobile suites separately because their module mocks differ.

### Frontend-only

- `bun run typecheck`
- `bun test common/frontend/tests`
- manually inspect `/command` and `/overlay` at Windows and Linux scale factors
- exercise keyboard/PTT/wake events when changing CommandBar lifecycle

### Tutor routing/provider

- Python compileall
- targeted pytest module(s), then full `common/python/tests`
- one JSON stdin smoke request to `common/python/main.py` with provider/network calls mocked or deliberately configured
- verify stdout contains only protocol records and final JSON

### Screen matching/coordinates/autopilot

- `test_coordinate_conversion.py`, `test_screen_dims.py`, `test_ui_map_cache.py`, `test_text_grounder.py`, `test_guidance_flow.py`
- frontend autopilot/guidance tests
- manual high-DPI, multi-monitor, active-window, ambiguous-label, and input-field cases
- confirm a blocked action remains blocked and a safe action still requires a match

### Linux backend/computer use

- computer-use, tools, vision planner/verifier, recovery, screenshot, window-selection, virtual-mouse, and app-inventory tests
- backend doctor/manual smoke on each desktop environment affected
- verify both preferred tool and fallback failure messages

### Tauri/WebSocket/mobile

- Rust tests after the Python bundle resource exists (or use an explicit development-safe test configuration)
- `BLINKY_TRANSPORT_MODE=release TAURI_CONFIG='{"bundle":{"resources":[]}}' cargo test --manifest-path common/src-tauri/Cargo.toml --locked tls_identity::tests::pinned_wss_round_trip_works -- --exact` verifies a real loopback TLS + WebSocket round trip with the generated SPKI pin
- From generated `common/mobile/android`, `./gradlew :blinky-secure-socket:testReleaseUnitTest` verifies Android accepts the matching leaf SPKI pin and rejects wrong, malformed, or missing certificate data
- `bun test common/mobile/tests` verifies mobile connection-state behavior, including retaining the authentication-rejection error after socket cleanup
- JSON and legacy protocol smoke tests, invalid token, missing token, loopback, and LAN client cases
- release WSS handshake with the persisted identity, correct/wrong SPKI pin, JSON auth acknowledgement, and rejection of query-token-only auth
- daemon restart behavior and concurrent request IDs
- mobile development WS discovery, release native WSS discovery/auth acknowledgement, reconnect, query streaming, and destructive command confirmation
- Sarvam proxy paths without exposing the key in logs

### WhatsApp

- service startup on an occupied port and frontend discovery
- QR/auth restore/logout
- REST and Socket.IO CORS from actual Tauri origins
- group/direct command authorization cases
- summarization with missing/invalid key, media, cache, and ntfy disabled/enabled

There is no automated WhatsApp test suite in this repository; changes here require adding focused tests or documenting manual evidence.

### AiCut

- four native CTest executables
- `common/python/tests/test_aicut_tool.py`
- `common/python/tests/test_file_transfer_aicut_intent.py` for explicit remote edits and mixed batches
- manual FFmpeg smoke with paths containing spaces and a disposable media fixture
- transcription/subtitle tests should not overwrite tracked sample media
