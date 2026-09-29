# Blinky — project memory

> Deep cua-driver reference (coordinate spaces, element picking, input routing, UWP limits,
> `type_text` bug) lives in **`CUA-DRIVER-NOTES.md`** next to this file. Read it before touching
> `windows/src-tauri/src/platform/cua.rs`.

## Architecture conventions

- **A synchronous `#[tauri::command]` that blocks freezes the whole window.** Tauri runs sync
  commands inline on the UI thread. Anything that spawns a process, writes to a pipe, or waits on
  a condition variable must be `async fn` + `tauri::async_runtime::spawn_blocking` (see
  `actuator()` in `common/src-tauri/src/lib.rs`).
- **Tauri ↔ Python sidecar talks JSON over stdout/stdin.** `common/python/main.py` emits events
  with `print(json.dumps({...}), flush=True)`. Anything writing to stdout corrupts the protocol —
  an embedded `AIAgent` MUST run `quiet_mode=True`.
- **Python entry point:** `common/python/main.py` — orchestrator + intent router
  (`DESKTOP_AUTOMATION`, `OPEN_APP`, `MEDIA_PLAYBACK`, `SYSTEM_SHORTCUT`, `WEB_SEARCH`,
  `VIDEO_EDIT`, `WHATSAPP`, `SCREEN_EXPLANATION`, `LOCATOR`, `INFORMATIONAL_CHAT`). Platform code
  lives in `windows/python/` and `linux/python/`. Tool registry: `common/python/tools/registry.json`.
- **Computer-use is split planner / actuator.** Planner = `computer_use/loop.py`,
  `step_planner.py`, `vision_planner.py`, `text_grounder.py`, `recipes.py`, `recovery.py`.
  Actuator = a `ComputerUseBackend` (ABC in `computer_use/backends/base.py`). **Call it via
  `computer_use/actuator.py`, not `computer_use.linux_mcp`** — the facade dispatches per platform
  (Linux → `linux_mcp`; Windows/macOS → cua-driver). `get_backend()` returns a singleton or
  `None` = "use the legacy Rust `SendInput` path". Env `BLINKY_COMPUTER_USE_BACKEND` = `auto` |
  `cua` | `native` | `hyprland` | `gnome` | `kde`.
- **The frontend autopilot clicks through Rust, not Python.** Bridge is
  `windows/src-tauri/src/platform/cua.rs`, wired into `windows.rs` (`click_element_impl` →
  `click_screen_point_impl` fallback), exposed as the `click_element` command + `clickElement()`
  in `common/frontend/src/lib/tauri.ts`.
- **Don't gate the AI cursor animation on the action.** The glide is GPU-composited CSS; it runs
  alongside the backend call. `autopilot.ts` used to await 620ms and `Overlay.tsx` ran a 600ms
  glide — ~1.2s dead time per step. Wait is gone, glide is 220ms. Keep any future delay well under
  the backend round trip (~0.4s).
- **MCP runs both directions:** server (`common/aicut/aicut_mcp.py` + `mcp_config.json`), client
  shim (`computer_use/linux_mcp.py`). **Skills** live in `.agents/skills` with
  `common/skills-lock.json` tracking source + hash.
- **Blinky's own click coordinate pipeline is verified correct — don't "fix" it.**
  `capture_screen()` grabs 2560×1600 then `thumbnail((1920,1080))` → 1728×1080, so `sx = 0.675`.
  UIA bounds are screen-absolute and get scaled **down** into screenshot space; the frontend
  `getPhysicalClickablePoint()` scales back **up** by `screen_width / width` (1.4815). Round trip
  is identity — a live probe clicked `(237,1422)` and the cursor landed at exactly `(237,1422)`.

## Decisions

- **2026-09-15** — Integrate **Hermes Agent** (Nous Research, MIT, Python) rather than
  reimplementing. Plan: `docs/HERMES-INTEGRATION-PLAN.md`. Route A (embed `AIAgent`); Route B
  (JSON-RPC out-of-process) if `uv` ↔ `.venv` reconciliation hurts. Phases 1 (cua-driver
  actuator) and 2 (MCP tool bus) are independent of Hermes and go first.
- **Rule: exactly one agent loop runs at a time.** `computer_use/loop.py` becomes a tool the brain
  calls, not a peer loop.

## Known constraints

- **The git object store is damaged.** Missing objects (`47afb5bb`, `394a190a`, `094b460e`,
  `469bec6e`); `git diff HEAD` fails. **Never `git stash`, and never trust `git checkout` /
  `git restore`** — a checkout can silently delete working-tree files it cannot write back
  (observed: `common/src-tauri/src/platform/mod.rs`, `windows/src-tauri/src/platform/windows.rs`,
  `common/frontend/src/CommandBar.tsx` all vanished mid-session → `error[E0583]`).
  - **Recovery order:** (1) `git ls-files -s <path>` — the INDEX is the authority and is often
    newer than HEAD; (2) `git cat-file -e <blob>` → if present, `git cat-file blob <blob> > <path>`;
    (3) only then fall back to `git clone --depth 1 https://github.com/KingSahil/Blinky.git <dir>`;
    (4) verify `git hash-object <path>` == index blob AND `git diff --stat -- <path>` is empty —
    **`git status --porcelain` can print `MM` from a stale stat cache even when bytes match.**
  - Find everything that vanished: `git ls-files -z | while IFS= read -r -d '' f; do [ -e "$f" ] || echo "$f"; done`
  - Do not `git fsck`-repair or re-init; the objects are gone, not dangling.
  - Helpers: `tmp/check_index.py` (scans `git ls-files -s` for unreadable blobs — 19 on
    2026-09-16), `tmp/walk_head.py` (verifies HEAD's tree is complete).
- **`git commit` fails outright when the parent's tree is incomplete** (`fatal: unable to read
  tree`). Build the commit object directly instead — additive, does not touch the worktree:
  `TREE=$(git write-tree); COMMIT=$(git commit-tree "$TREE" -p HEAD -F <msgfile>);
  git update-ref refs/heads/main "$COMMIT"`.
- **`git add` does NOT repair a missing index blob** (trusts the stat cache, exits 0). Repair
  without touching the worktree:
  `sha=$(git hash-object -w --path=<p> <p>); mode=$(git ls-files -s <p> | awk '{print $1}');
  git update-index --cacheinfo "$mode,$sha,<p>"`. `touch <files> && git add` also works but
  **bumps mtimes and fires file watchers** — it once triggered a Tauri rebuild and restarted
  `blinky.exe` mid-session. Never `touch` files under a watched tree while a dev server runs.
- The full `pytest common/python/tests/` run hangs on a pre-existing test — run files
  individually. `test_screenshot_tool.py` fails on Windows by design.
- **`common/mobile` (Expo) — beware bad merges.** Merge `f8146b6` ("Merge branch 'main' into
  assembly_ai") resolved `App.tsx` to the assembly_ai side and silently dropped main's work:
  `activeTab`, `showSplash`, `isLightOn`, the PIN modal state, the Files screen wiring, font
  loading, and attached-file support — leaving a file that neither parsed (unclosed `<Modal>`) nor
  typechecked (undefined identifiers). Compare `git show <rev>:common/mobile/App.tsx` against
  both parents before trusting any merge result here. Restored 2026-09-29 from `6bd6b00` +
  re-applied the AssemblyAI STT block.
- **Three-tier check for `common/mobile` (Expo), in increasing cost:** (1) `tmp/jsxcheck.js`
  parses a `.tsx` with `@babel/parser` (`node tmp/jsxcheck.js <files>`) — use it to bisect which
  revision of a file is syntactically valid; (2) `node node_modules/typescript/bin/tsc --noEmit
  -p tsconfig.json` — Babel only catches syntax, so this is what finds the undefined identifiers
  a bad merge leaves behind (invisible to the bundler until runtime); (3) `bun test` (23 tests)
  then `./node_modules/.bin/expo.exe export --platform android` for a real Metro bundle.
  `npx tsc` does **not** work here — point node at `node_modules/typescript/bin/tsc` directly.
- **`bun install --lockfile-only`** re-syncs `bun.lock` without touching `node_modules` — use it
  instead of a plain `bun install` when the lockfile is stale but the app already works.
- **Mobile ↔ PC voice-key plumbing lives in Rust, not Python.** `common/src-tauri/src/websocket.rs`
  handles `get_sarvam_key` → `{type:"sarvam_key"}` and `get_assemblyai_key` →
  `{type:"assemblyai_key"}` from `SARVAM_API_KEY` / `ASSEMBLY_AI_API_KEY`. Grepping
  `common/python` for "sarvam" finds nothing.
