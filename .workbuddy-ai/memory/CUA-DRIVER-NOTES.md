# cua-driver (0.28.1) reference — Blinky's Windows/macOS actuator

Split out of `MEMORY.md` because that file has a size budget. Read this before touching
`windows/src-tauri/src/platform/cua.rs` or anything that drives the desktop.

Installed at `%LOCALAPPDATA%\Programs\Cua\cua-driver\bin\cua-driver.exe`, daemon-backed
(named pipe `\\.\pipe\cua-driver`), 57 tools.

## Transport — a latency decision, not a style one

- `cua-driver call <tool> '<json>'` costs **~1.45s of process startup per call** (even for a
  28-byte reply). The full click ladder ≈ **8s** — that is the "lag" between the AI cursor
  arriving and the click landing.
- `cua-driver mcp` — JSON-RPC over stdio on one long-lived child: 0.006s / 0.08s / 0.15s,
  ladder **~0.4s**. This is what the Rust bridge uses, behind a `Mutex`.
  **Drain both pipes continuously** — a child blocked on a full stdout pipe never exits, and
  that is the real cause of `unparseable driver output`, not a parsing bug. Exits 0 on stdin
  EOF, so closing Blinky reaps it.
- One-shot CLI introspection is still the fastest way to read schemas: `cua-driver mcp` →
  `tools/list` gives all 57 tools with full `inputSchema`. **Those descriptions are
  authoritative about coordinate spaces; the prose `--help` is not** (see below).

## Coordinate spaces — the driver's prose lies; its data does not

- Coordinates are **true screen pixels** (`get_desktop_state` space, e.g. 2560×1600 @ scale
  1.5). Desktop-scope clicks use `scope="desktop"` with `pid` omitted.
- **`frame` is PHYSICAL window pixels, and so is window-scope `x, y`.** The driver documents
  window-scope `x, y` as "window-local screenshot pixels — same space as the PNG
  `get_window_state` returns". **That is wrong.** Measured on a 2560×1528 window with a 1456
  cap: frames reach `max_right=2560, max_bottom=1528` and the `Window` element's frame is
  `{x:0,y:0,w:2560,h:1528}` — not the 1456×869 the screenshot reports. Settled by clicking the
  same element both ways: physical → `route: accessibility`, page acted, cursor unmoved;
  screenshot → `route: synthetic_events`, no-op.
  **Conversion is subtraction of the window origin and nothing else.**
  Believing the prose caused the "it always clicks accounts" bug: `window_local()` scaled by
  `min(1, max_image_dimension / max(w,h))` (0.56875), putting every window-scope click
  **1.758× too close to the window's top-left**. Settings nav "System" at physical `(234,302)`
  was clicked at `(133,172)`, which is inside the account card (`x 9..443, y 74..187`). The AI
  cursor is drawn at the true screen point; the click was delivered at the scaled one.
  `frame` keys are `x/y/w/h` (no `width`/`height`) and do not require `include_screenshot`.
  `max_image_dimension()`, `window_local_reported()` and `scratch_screenshot()` existed only
  for that scaling and are deleted — no branch of the click path requests a screenshot.
- **`delivery_mode` is IGNORED in desktop scope.** A desktop-scope click returns
  `{delivery: {mode: "not_applicable"}, route: "global_input"}` — global input injection, so
  **the real pointer moves**. There is no background desktop click. Both **window-scope** rungs
  are genuinely background. Verified live: window-scope clicks do not move the cursor.
- `screenshot_out_file` paths come back `\\?\`-prefixed — strip before `Path()`.
- `list_windows` returns rich `windows[]` and `_legacy_windows[]`; prefer `windows`, and use
  `on_screen_only: true` (cheaper, drops the phantom `-32000` minimized entries).

## Targeting a window

- The driver's `window_id` **IS the Win32 HWND** (verified: Settings 1051900, Edge 1312662,
  IDE 2689014), so a hit-test result joins onto `list_windows` exactly. Resolve the target with
  `WindowFromPoint` → `GetAncestor(GA_ROOT)`; fall back to `GetForegroundWindow`, then to a
  `z_index` scan.
- The hit-test **skips layered/transparent windows for free**, which is why Blinky's fullscreen
  always-on-top overlay needs no special reasoning. Requires a **DPI-aware process**
  (`shcore.SetProcessDpiAwareness(2)`) — Tauri is; a bare Python probe is not (it saw
  1707×1067 instead of 2560×1600 and `WindowFromPoint` returned NULL).
- **`z_index` IS a faithful stacking order** — verified against `EnumWindows` top→bottom, exact
  match; a faithful A/B replay against the hit-test over six points gave `agree=6, disagree=0`.
  So treat the hit-test as *robustness*, not as the fix for the Settings misclick — that was the
  coordinate space and the `select` filter.
- Blinky's own highlight overlay sat at `z_index` 18, **above Edge at 15**; exclude Blinky's own
  windows **by pid** (`std::process::id()`) — exact — plus a title list as backstop.
- A covered window stays unreachable: with the IDE maximised over Settings, `points hit-testing
  to Settings: 0` is the *correct* answer, and a test point belonging to another window proves
  nothing about Settings.
- **Trap: omitting `window_id` lets the driver auto-resolve a pid's window and pick the wrong
  one.** A window-scope click at `(700,400)` reported landing at screen `(710,1890)`, which
  looked like a broken coordinate formula. The real cause: pid 37932 owned *two* windows and the
  driver chose a phantom `219x30@9,1489` one — `9+700=709`, `1489+400=1889`. The formula was
  right; the window was wrong. **Always pass an explicit `window_id`.**

## Sessions, cursor, delivery

- `delivery_mode="background"` is the default and the mandatory first attempt. Never pass
  `foreground` preemptively; escalate only on a `background_unavailable` error, gated by
  `BLINKY_CUA_ALLOW_FOREGROUND` (default on).
- Sessions idle-expire (~5 min) and **omitting the label mints a NEW implicit session per CLI
  call**. Both avoided by one stable named session with auto-revival: `start_session`,
  re-assert the cursor flag, retry once. See `SESSION`, `revive_session`, `send` in `cua.rs`.
- `set_agent_cursor_enabled` **REQUIRES `session`** (`"required": ["session","enabled"]`).
  Calling it with just `{"enabled": false}` fails validation and the driver's second cursor
  keeps appearing. Blinky keeps `cursor_visible: false` on its `blinky` session.
- `Cua.AgentCursorOverlay` is a 2560×1600 always-on-top window owned by the daemon, created
  `WS_EX_TRANSPARENT | LAYERED | NOACTIVATE | TOOLWINDOW` — i.e. **click-through**, it never
  swallows clicks. Thin `cua-driver.exe` clients don't always exit and each owns one, so strays
  accumulate (one measured at `z=16`). They are the "phantom second cursor" if a session leaves
  its cursor enabled. `cua-driver stop` clears them.

## Reading driver responses

- **A refusal arrives as a SUCCESSFUL tool call**: `{"refusal": {"code","message"}, "status":
  "refused"}`, often with `isError` unset. Checking `isError` alone reads a refused click as a
  completed one and suppresses the fallback that would have made it work. Check `refusal` /
  bad `status` explicitly.
- **`get_window_state` errors put the human reason in `content[].text`**, with only a machine
  code in `structuredContent` (`{"code": "tool_invocation_failed"}`). Read the text block.
- **`degraded` is not `empty`.** A minimized window reports `x/y = -32000` and
  `get_window_state` returns `degraded: true` + `ax_tree_empty` + `screenshot_error: cannot
  capture minimized window`. Check `WindowInfo.supported` (False for minimized/off-screen) and
  `last_snapshot_degraded`; `get_app_state` surfaces `degraded` / `degraded_reason` so callers
  fall back to OCR.
- **The `query` projection is unreliable for picking a control.** Measured on Chromium:
  `query="Guide"` returned a `Group` named `guide-button` plus an unrelated hyperlink, but
  **omitted the real `Button` named `Guide`**. Fetch the whole tree and rank locally.
- `element_index` clicks need the `snapshot_id` from a prior `get_window_state` for the same
  `(pid, window_id)`; `get_window_elements()` caches it. **A bare `element_index` is always
  REFUSED** (`snapshot_id_required`) — prefer `element_token` (opaque, e.g. `s00000001:0`,
  carries window + snapshot with it). **Any later `get_window_state` on that window invalidates
  prior tokens** (`stale_element_token`, `s00000001` → `s00000002`).

## Input routing

- `route: "accessibility"` = the driver hit-tested and drove an element (works, incl. XAML).
- `route: "synthetic_events"` = raw mouse events posted to the window — Win32 honours them,
  **XAML silently ignores them** (measured: a window-scope pixel click over a Settings nav item
  reported success and changed nothing).
- `route: "global_input"` = real global injection, moves the real cursor.
- All three report `effect: "unverifiable"`, so **the route is the only signal**. Do not
  auto-escalate a window-scope pixel click to desktop scope — that moves the real cursor and
  would double-act on Win32. Log it instead (`warn_inert_pixel_click`).
- **Never target an unlabelled element.** Chromium exposes full-window `Group` nodes that
  advertise `invoke` but do nothing; the click reports success while doing nothing and
  suppresses the point-click fallback.

## Picking the right element — two filters that each caused a bug

- **Requiring an `invoke` action rejects every Windows 11 Settings nav item.** They are plain
  `ListItem`s advertising only `select`, so an invoke-only filter made `pick_element` return
  `None` for every nav label and pushed all nav clicks onto the pixel rung. The driver drives a
  `select`-able element by token fine (`route: accessibility`, cursor unmoved, page navigates).
  Filter on `ACTIVATING_ACTIONS` = invoke, select, toggle, expand, collapse, check, uncheck,
  press, click, open. **Exclude `focus`, `scroll_into_view`, `set_value`** — not activations;
  accepting them lets `pick_element` report success while doing nothing.
- **The AI cursor and the click must be derived from the same signal, and that signal is the
  point.** `pick_element` used to rank label matches by `(exactness, name.len(), role)`,
  discarding `x, y` whenever a label was present — which is always. The cursor then glided to
  the right control while a different one was invoked ("the cursor goes in the right position
  … it clicks something else"). Rank by `(exactness, distance, length, role)`: proximity breaks
  ties, exactness still outranks proximity. Duplicate labels make the tie the common case —
  Settings has `Home` as both a `ListItem` and a `Button`, and `More options` and
  `View all devices` twice each.

## `type_text` / `press_key` — an OPEN BUG, not a design choice

`cua::scroll` resolves the window under the point and stays window-scoped, so it no longer drags
the real cursor. But `cua::type_text` dispatches a bare `{"text": ...}` and `cua::press_key` a
bare `{"key": ...}` — no `pid`, no `window_id`, no `scope`. The driver accepts all three (its
`type_text` / `press_key` schemas expose `pid`, `window_id`, `scope`, `element_token`) and its
docs say that without them it falls back to the **focused** window. So typing is not reliably
targeted. Measured against Notepad (pid 40936, wid 5178132):

| variant | isError | route | text landed |
|---|---|---|---|
| bare `{"text":…}` (what Blinky does today) | **True** `tool_invocation_failed` | — | **no** |
| `+pid +window_id +scope` | None | `synthetic_events` (+ `escalation: {reason: delivery_failed}`) | yes — appended in place |
| `set_value` on the field's element token | None | **`accessibility`** | yes — replaced content |

`debug_window_info` reported `host exe=notepad.exe, xaml_routing_recommended=True`, so the
"Win32 vs XAML" heuristic is **wrong** — the driver keys on **EXE basename**, not toolkit.
Conclusion: bare `type_text` is simply broken; targeting fixes it; `set_value` is the cleanest
rung. Blinky's realistic use is typing into a *focused empty* field, where escalating to global
input is acceptable.

## The typed `browser_*` family

`browser_prepare`, `browser_click`, `browser_type`, `browser_pointer`, `browser_navigate`,
`get_browser_state` drive Chromium/Electron over CDP — background **and** reliable, with
`browser_click` taking viewport CSS px or a page `ref`. **Gated:** `browser_prepare` refuses
without an explicit launch grant (`--grant existing-profile`), so it is Phase 2 work, not a
dependency today. It is the right rung for Edge/Chrome/Discord/Spotify if Chromium drops posted
synthetic events.

## Stage costs over the persistent transport

`list_windows` (`on_screen_only: true`) 0.10–0.14s; `get_window_state` **tree only** 0.10–0.19s;
`get_window_state` **capture-only** 0.4–0.9s (avoid unless you need pixels); `click` 0.09s.
Whole ladder ≈ 0.35s.

## UWP hosting determines what is possible — and it varies within one app

- Measured: a Settings window hosted by `ApplicationFrameHost.exe` returned **79–85 elements**
  on the first call, so the element rung *is* viable. A Settings window hosted by
  `SystemSettings.exe` returned **0 elements** on every attempt with `degraded: true`,
  `degraded_reason: "ax_tree_empty"`, `escalation.recommended: "px"` — the driver's own advice
  is to **re-snapshot**, which `window_tree()` now does once after a 150ms settle.
- For pixel input the split is by window class: an **`ApplicationFrameWindow`** accepts
  window-scope synthetic clicks; a bare **`Windows.UI.Core.CoreWindow`** refuses them
  (`tool_invocation_failed`, with the contradictory message `"The operation completed
  successfully. (0x00000000)"` — not a units problem; downscaled px, physical px and an
  out-of-bounds point all fail identically). Chromium is fine (Edge: 115–324 elements).
- **Correction:** an earlier note concluded Settings has **no** background path, assuming it is
  always a bare CoreWindow. Wrong for the case that matters. On a live
  `ApplicationFrameHost.exe` instance (2560×1528, **84 elements**) the **element rung works
  fully in the background** — nav items resolve by `select`, the driver drives them by token
  with `route: "accessibility"`, the real cursor stays put, the page navigates. Only the *pixel*
  rung is inert there. Accurate statement: **Settings is reachable in the background, but only
  through the element rung.** `SystemSettings.exe`-hosted instances still return 0 elements.

## Other Windows limits

- **UIPI:** a medium-integrity process cannot drive an elevated (Administrator) window —
  `click()` reports success but does nothing.
- Windows over SSH lands in Session 0 (no interactive desktop). Drive from RDP/console.
