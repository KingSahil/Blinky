# Blinky — project memory

> Deep cua-driver reference (coordinate spaces, element picking, input routing, UWP limits,
> `type_text` bug) lives in **`CUA-DRIVER-NOTES.md`** next to this file. Read it before touching
> `windows/src-tauri/src/platform/cua.rs`.

## Architecture conventions

- **A synchronous `#[tauri::command]` that blocks freezes the whole window.** Tauri runs sync
  commands inline on the thread that dispatched the IPC message — the UI thread on Windows. No
  spawn, so a slow command stalls the event loop: no repaints, no event delivery, window reports
  "not responding". Anything that spawns a process, writes to a pipe, or waits on a condition
  variable must be `async fn` + `tauri::async_runtime::spawn_blocking` (see `actuator()` in
  `common/src-tauri/src/lib.rs`). Invisible until a command gets slow — the actuator commands
  were fine for milliseconds of `SendInput` and only became a freeze once they talked to
  cua-driver.

- **Tauri ↔ Python sidecar talks JSON over stdout/stdin.** `common/python/main.py` emits events
  with `print(json.dumps({...}), flush=True)`. Anything writing to stdout corrupts the protocol —
  an embedded `AIAgent` MUST run `quiet_mode=True`, and dependency managers must not print
  banners into the pipe.

- **Python entry point:** `common/python/main.py` — orchestrator + intent router
  (`DESKTOP_AUTOMATION`, `OPEN_APP`, `MEDIA_PLAYBACK`, `SYSTEM_SHORTCUT`, `WEB_SEARCH`,
  `VIDEO_EDIT`, `WHATSAPP`, `SCREEN_EXPLANATION`, `LOCATOR`, `INFORMATIONAL_CHAT`). Platform code
  lives in `windows/python/` and `linux/python/`, injected onto `sys.path` by `main.py`. Tool
  registration is `common/python/tools/registry.json`; `utils/generalizer.py` +
  `utils/sufficiency_checker.py` auto-generalize and verify outputs.

- **Computer-use is split planner / actuator.** Planner = `computer_use/loop.py`,
  `step_planner.py`, `vision_planner.py`, `text_grounder.py`, `recipes.py`, `recovery.py`.
  Actuator = the selected `ComputerUseBackend`, behind `linux_mcp_compat`-style signatures
  (`list_windows`, `get_app_state`, `click_element`, `type_text`, `press_key`, `screenshot`,
  `doctor`). **Call it via `computer_use/actuator.py`, not `computer_use.linux_mcp`** — the
  facade dispatches per platform (Linux → `linux_mcp`; Windows/macOS → cua-driver) and keeps the
  old dict shapes. `tools.py` gates on `_backend_error()`; Linux is deliberately ungated.
  ABC lives in `computer_use/backends/base.py` (`linux/python/backend/abc.py` is a re-export
  shim). `get_backend()` returns a singleton or **`None`** = "use the legacy Rust `SendInput`
  path". Env `BLINKY_COMPUTER_USE_BACKEND` = `auto` (default) | `cua` | `native` | `hyprland` |
  `gnome` | `kde`.

- **The frontend autopilot clicks through Rust, not Python.** `run_python_worker` spawns a fresh
  interpreter per request, so a Python click would cost a startup per click. Bridge is
  `windows/src-tauri/src/platform/cua.rs`, wired into `windows.rs` (`click_element_impl` →
  `click_screen_point_impl` fallback) and exposed as the `click_element` command +
  `clickElement()` in `common/frontend/src/lib/tauri.ts`.

- **Don't gate the AI cursor animation on the action.** The glide is a GPU-composited CSS
  animation inside the overlay window, so it runs alongside the backend call. `autopilot.ts` used
  to await 620ms and `Overlay.tsx` ran a 600ms glide — ~1.2s dead time per step. The wait is gone
  and the glide is 220ms. Keep any future delay well under the backend round trip (~0.4s).

- **MCP already exists in two directions:** server (`common/aicut/aicut_mcp.py` +
  `mcp_config.json`), client shim (`computer_use/linux_mcp.py`). **Skills** live in
  `.agents/skills` with `common/skills-lock.json` tracking source + hash; not yet the
  agentskills.io `SKILL.md` standard.

- **Blinky's own click coordinate pipeline is verified correct — don't "fix" it.**
  `capture_screen()` grabs 2560×1600 then `thumbnail((1920,1080))` → 1728×1080, so `sx = 0.675`.
  UIA bounds are screen-absolute and `scale_uia_items_to_screenshot()` scales them **down** into
  screenshot space; OCR already runs on the downscaled image; the frontend
  `getPhysicalClickablePoint()` scales back **up** by `screen_width / width` (1.4815). The round
  trip is identity — a live probe clicked `(237,1422)` and the cursor landed at exactly
  `(237,1422)`.

## Decisions

- **2026-09-15** — Chose to integrate **Hermes Agent** (Nous Research, MIT, Python) rather than
  reimplement it. Plan: `docs/HERMES-INTEGRATION-PLAN.md`. Route A (embed `AIAgent`) for the
  brain; Route B (drive out-of-process over JSON-RPC) if the `uv` ↔ `.venv` dependency
  reconciliation proves painful. Phases 1 (cua-driver actuator) and 2 (MCP tool bus) are
  independent of Hermes and go first.
- **Rule: exactly one agent loop runs at a time.** Blinky's `computer_use/loop.py` becomes a tool
  the brain calls, not a peer loop. Two loops cause duplicate clicks and runaway iterations.

## Known constraints

- **Do not use `git stash` in this repo, and do not trust `git checkout` / `git restore` to be
  harmless.** The object store is damaged — `git fsck` reports invalid reflog entries and missing
  objects (`47afb5bb`, `394a190a`, `094b460e`, `469bec6e`), and `git diff HEAD` fails outright. A
  `git stash push` writes into that damaged store and leaves an unreadable stash entry.
  **A checkout can silently delete working-tree files it cannot write back.** Observed:
  `common/src-tauri/src/platform/mod.rs`, `windows/src-tauri/src/platform/windows.rs` and
  `common/frontend/src/CommandBar.tsx` vanished mid-session, `git checkout -- <paths>` failed with
  `unable to read sha1 file of …`, and the build broke with `error[E0583]: file not found for
  module platform`.
  **Recovery: check the INDEX before cloning.** A `git clone --depth 1
  https://github.com/KingSahil/Blinky.git <dir>` recovers HEAD's bytes, but **HEAD is not always
  what you want** — the index can hold a *staged* version newer than HEAD, and restoring HEAD
  silently rolls that work back. Measured on `common/python/computer_use/tools.py`: index blob
  `0fbe70b1` (88180 bytes) vs HEAD blob `47afb5bb` (86722 bytes) — and `47afb5bb` is one of the
  **missing** objects, so HEAD's copy is unrecoverable while the staged copy is readable.
  Order: (1) `git ls-files -s <path>` — the index is the authority, and shows whether the file is
  even tracked; (2) `git cat-file -e <blob>` — if PRESENT, restore with
  `git cat-file blob <blob> > <path>`; (3) only if the index blob is unreadable, fall back to the
  clone; (4) verify `git hash-object <path>` == the index blob and `git diff --stat -- <path>`
  empty — **an empty `git diff` is the real proof** (`git status --porcelain` can print `MM` from
  a stale stat cache even when the bytes match). To find everything that vanished, don't wait for
  a build error: `git ls-files -z | while IFS= read -r -d '' f; do [ -e "$f" ] || echo "$f"; done`.
  Do not `git fsck`-repair or re-init; the objects are gone, not dangling.

- **`git commit` FAILS outright in this repo when the parent's tree is incomplete** —
  `fatal: unable to read tree (<sha>)`, exit 128. `-q` does not help: git genuinely needs the
  parent's tree, not just for the summary. The commit object can still be built directly:
  ```
  TREE=$(git write-tree)
  COMMIT=$(git commit-tree "$TREE" -p HEAD -F <msgfile>)
  git update-ref refs/heads/main "$COMMIT"
  ```
  That is exactly what `git commit` does internally, minus the diff summary it cannot compute.
  It is additive and does not touch the worktree.

- **The INDEX can reference missing blobs too, and `git write-tree` reports them one at a time**
  (`error: invalid object 100644 <sha> for '<path>'`). Scan for all of them at once with a
  script over `git ls-files -s` — see `tmp/check_index.py`. On 2026-09-16 there were **19**.

- **`git add` does NOT repair a missing index blob.** It trusts the stat cache, decides the file
  is unchanged, and leaves the broken entry in place — exit code 0, nothing fixed.
  Repair it **without touching the worktree**:
  ```
  sha=$(git hash-object -w --path=<path> <path>)
  mode=$(git ls-files -s <path> | awk '{print $1}')
  git update-index --cacheinfo "$mode,$sha,<path>"
  ```
  Verified in a scratch repo: recomputed sha matched byte-for-byte, mtime unchanged, `write-tree`
  returned 0. The 19 real entries were repaired with `touch <files> && git add <files>` instead —
  which works, but **`touch` bumps mtimes and fires file watchers**: it triggered a Tauri rebuild
  on `common/src-tauri/src/websocket.rs`, restarted `blinky.exe` mid-session, and the restarted
  process exited 1 with an empty stderr. **Never `touch` files under a watched tree while a dev
  server is running.**

- **Measured damage, 2026-09-16.** Old HEAD `d4ca36d` was missing **4 trees** —
  `windows/` (`51d00719`), `linux/src-tauri/` (`2c002c26`), `common/src-tauri/src/` (`1f208edc`),
  `common/frontend/` (`4e8e29fa`) — plus 1 blob, `common/python/computer_use/tools.py`
  (`47afb5bb`). History traversal breaks further back at `c7c1872b` (`094b460e` missing).
  Notably the 4 missing trees are exactly the directories the cua-driver work touches.
  After commit `62b585b8`, **that commit's own tree is complete** (81 trees walked, 0 missing),
  so `git status` and `git diff HEAD` work again — but `git show HEAD`, `git log --stat` and
  anything that diffs against the parent still fail, and **`git push` is at risk** for the same
  reason. Verify with `tmp/walk_head.py`.

- The full `pytest common/python/tests/` run hangs on a pre-existing test — run files
  individually. `test_screenshot_tool.py` fails on Windows by design (it patches the Linux-only
  `backend.capture` package).
