# Blinky — Security Remediation "God Plan"

> Generated 2026-08-07 from the full-codebase security review.
> **Excluded (keep as-is, per user):** forced `GDK_BACKEND=x11` in `main.rs`; the LLM-code execution path (agent_router codegen + generalizer) — both needed for now.
> All remaining review priorities are covered below. Each item = actionable, tested fix.

---

## Phase 0 — Write the plan (this doc) ✅

## Phase 1 — Remote-control WebSocket hardening (ship-blocker)

**Priority 1 · [ws-auth]** `common/src-tauri/src/websocket.rs`
- Bind stays on a configurable host (LAN remote is the feature), but **every command must be authenticated**.
- Add a secret token flow:
  - Generate/persist a per-install `BLINKY_REMOTE_TOKEN` in `.env`.
  - Require it on the WebSocket handshake (`?token=` query param captured by the existing `accept_hdr_async` path-capture callback) OR as the first authenticated frame.
  - Reject the connection if the token is absent/invalid.
- Optionally restrict `power_off/restart/sleep/lock` to *also* require a desktop-side confirmation before executing (defense in depth), at minimum require auth.

** [mobile-auth] `common/mobile/`
- The Expo remote must send the token. Add a token field to the connect UI + pass `?token=` in the `ws://` URL in `usePCWebSocket.ts`.

## Phase 2 — Kill LLM-as-code-executor (RCE)

**SKIPPED per user** — the LLM-code execution path (agent_router codegen + generalizer persistence) is needed for now and left in place. Revisit later. (Note for future: `generalizer.py` auto-executes and persists LLM code at daemon start — when ready to fix, this is the active RCE surface.)

## Phase 3 — Credential & frontend exposure

** [keys] `common/src-tauri/src/lib.rs`**
- **FINDING (during execution):** the renderer legitimately needs the API keys — the frontend calls `wss://api.sarvam.ai` directly with the subscription key (CommandBar.tsx:409,582,810). Removing keys from `get_settings` would break the app. Keys stay; mitigation = strict CSP (below) + `get_sarvam_key` WS endpoint is now auth-gated (Phase 1).
- **Applied:** replaced `"csp": null` with a strict CSP: `connect-src` limited to `self`, Tauri IPC, `127.0.0.1:9001`, Sarvam cloud, and the Vite dev server. This caps the exfiltration blast radius of any webview XSS — the keys can no longer be sent to attacker-controlled origins via fetch/WebSocket.

** [keys] `common/src-tauri/tauri.conf.json`**
- Replace `"csp": null` with a strict CSP (no `unsafe-eval`/`unsafe-inline` for scripts where feasible; allow-inline styles). Reduce webview XSS blast radius to the rich IPC surface.

## Priority 4 — Correctness & dead code

** [dedupe] `agent_router.py`, `main.py`**
- Delete ghost artifacts: `common/python/tools/temp_candidate_*.py`, unused codegen constants, the never-true `new_tool_generated` branch.
- Do NOT re-architect the whole triplicated router in this pass (out of security scope) — just remove dead/ghost code.

** [think] `common/python/ai/ollama_client.py`**
- Add `"think": false` to the request body (gemma4 = thinking model) so token budget & latency aren't consumed by chain-of-thought.
- Validate the returned JSON against the expected shape in `_validate_response` instead of partial `re.search` recovery.

## Priority 5 — input-injection hygiene

** [sendskeys] `common/python/computer_use/tools.py`**
- `_open_app_via_windows_search_windows` calls `send_keys(app_name)` — raw text with pywinauto-modifier interpretation (`{..}`, `^`, `%`, `+`).
- Fix: whitelist enforced (already partially via `normalize_app_name`), but do **not** pass interpreted modifiers; type via `send_keys` with an escape/whitelist or use the verified windows-search-result path only.

** [githygiene] `.gitignore` + committed artifacts**
- Add `python/tools/registry*.json`, `common/python/python/cache/`, `*.temp_candidate*`, `data/users/.../runtime`.
- `git rm --cached` committed generator artifacts + WhatsApp runtime `settings.json`.

** [wa] `common/whatsapp_backend/server.js`**
- Default CORS `*` → require `ALLOWED_ORIGINS`; validate session ownership on `chat.sendSeen` + gate `/api/summarise` → `sendNtfy` fan-out behind auth/origin.

## Phase 6 — Verify ✅

- Rust: `cargo check` clean; **12/12 unit tests** pass (6 new: token_equals, extract_query_token, uri_without_query, generate_remote_token).
- Python: **227 passed**; 18 failures are **pre-existing environment issues** (confirmed identical on pristine code via stash-test: /dev/uinput missing, network-dependent searxng/spotify, LLM-dependent routing). **Zero regressions from this pass.**
- Fixed latent test bug: `test_browser_agent.py` asserted on an ignored `controller` and **opened real browser tabs** (webbrowser.open) when run — now mocked, 4/4 pass.
- Mobile TS (`tsc --noEmit`) clean; Frontend TS clean.
- Token generator verified: 32-hex, unique per call.
- **Bonus fix:** `common/src-tauri/src/platform/mod.rs` re-exported `execute_volume_*` from `platform_impl` (linux.rs) where they don't exist — **pre-existing Linux compile break**; moved to `power_impl` re-export (`pub use power_impl::*`), crate now compiles.

---

## Priority map (review → this plan)
| Review priority | Plan item |
|---|---|
| 1 WS auth + 2 power gating | ws-auth, mobile-auth |
| 3 remove LLM-code exec | **SKIPPED per user** |
| 4 keys to renderer + CSP | keys |
| 5 dead code + triplicated router | dedupe (ghost artifacts only, not codegen) |
| 6 send_keys injection | sendskeys |
| 7 think:false + JSON validation | think |
| 8 committed secrets/artifacts | githygiene |
| 9 GDK_BACKEND | **SKIPPED per user** |
| 10 WhatsApp CORS/ntfy | waits |