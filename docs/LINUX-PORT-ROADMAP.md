# Blinky Linux Port — Roadmap (Windows → Hyprland → GNOME → KDE)

> Companion to docs/SECURITY-REMEDIATION.md. Strategy: **port Windows components one-by-one,
> in dependency order, Hyprland-first.** Replace the `computer-use-linux` MCP layer with an
> in-repo `ComputerUseBackend` ABC (adopted from the Hermes harness contract), implemented
> natively on Hyprland (ydotool / grim / hyprctl / wtype). No cua-driver, no MCP.

---

## Decision log (from brainstorming)

- **Rejected:** `computer-use-linux` MCP (mcp_bridge.rs + linux_mcp.py + binary). It is a KDE/X11-
  oriented external binary and the whole layer gets deleted.
- **Rejected:** Hermes' cua-driver backend. Its Linux story is "X11 today, Wayland via XWayland" —
  useless on pure Wayland/Hyprland. (Also not installed here: `~/.local/bin/cua-driver` is a
  broken symlink.)
- **Adopted:** the **backend contract** from `~/.hermes/hermes-agent/tools/computer_use/backend.py`
  (ABC: capture / click / type_text / key / scroll / drag / list_apps / list_windows / focus_app /
  set_value + UIElement / CaptureResult / ActionResult). MIT-compatible, self-contained, no deps.
- **Input backbone decision (Option A):** Rust `linux.rs` owns physical input via **ydotool + wtype**
  (parity with Windows `windows.rs` SendInput), so the frontend autopilot click path
  (Tauri command → linux.rs) works. The Python backend reuses the same binaries for the loop.
- **Hyprland-first:** toolchain verified on this machine: hyprctl ✓ grim ✓ slurp ✓ ydotool ✓;
  missing: wtype (typing), tesseract (OCR) — install via pacman.
- **Salvage from old linux/:** WaylandPortalCaptureStrategy (compositor-agnostic portal capture),
  app_inventory structure, KWinGrimCaptureStrategy pattern (grim is wlroots-native → works on Hyprland).

---

## Target directory structure (new `linux/`)

```
linux/
├── python/
│   ├── backend/                  # NEW — the ABC + implementations
│   │   ├── abc.py                #   ComputerUseBackend + dataclasses (adopted contract)
│   │   ├── hyprland.py           #   HyprlandBackend: hyprctl + ydotool + wtype + grim
│   │   ├── gnome.py              #   GnomeBackend (phase 8) — portal + AT-SPI
│   │   ├── kde.py                #   KDEBackend (phase 8) — kwin + AT-SPI
│   │   ├── capture.py            #   portal capture (salvaged) + grim full-screen
│   │   ├── window.py             #   hyprctl activewindow/clients → bounds + pid + app_id
│   │   └── input.py              #   ydotool/wtype wrappers (click/scroll/type/key)
│   ├── app_inventory.py          # keep/salvage; add `hyprctl clients` + .desktop scan
│   └── (delete: wayland_vision.py, window_linux.py, linux_capture.py → folded into backend/)
├── src-tauri/src/platform/
│   ├── linux.rs                  # REWRITE: click/scroll/type via ydotool/wtype (Option A)
│   └── power.rs                  # keep (systemctl/amixer/pactl/loginctl), + hyprctl lock
└── requirements.txt              # + pyatspi (future), wtype/tesseract are system pkgs
```

**common/ changes:** delete `common/python/computer_use/linux_mcp.py`; `mcp_bridge.rs` + `mod mcp_bridge`
in lib.rs deleted; `tools.py` linux tools (`list_windows_tool`, `get_app_state_tool`, `click_element_tool`,
`type_text_tool`, `screenshot_tool`, `open_app_tool_linux`) re-point from `linux_mcp` → `linux.backend`.

---

## Port order (dependency-driven) — 9 phases

### Phase 0 — Environment + skeleton
- `sudo pacman -S wtype tesseract` (verified missing)
- Start ydotool daemon (needs root: `sudo systemctl enable --now ydotool` or uinput group) — verify with `ydotool click 0xC0`
- Copy ABC contract into `linux/python/backend/abc.py` (strip cua-specific fields: element_token,
  delivery_mode/verification ladder can stay as optional additive fields)
- Restructure dirs per target structure; git rm old linux/python files (keep in git history)

**Windows parity ref:** `windows/python/*` + `windows/src-tauri/src/platform/*`

### Phase 1 — Capture (no dependencies; first visual milestone) ✅ DONE
- `backend/capture.py`: grim-first cascade — `GrimFullscreenCaptureStrategy` (multi-monitor stitch)
  + `GrimWindowCropCaptureStrategy` (active-window crop via hyprctl bounds, scale-aware)
  + `WaylandPortalCaptureStrategy` (salvaged, compositor-agnostic fallback)
- `backend/window.py`: `hyprctl activewindow/clients/monitors -j` → WindowInfo + screen_size
- `backend/portal.py`: portal capture salvaged (python-dbus + CLI-dbus fallback)
- `backend/hyprland.py`: HyprlandBackend (Phase 1: capture + window + screen; input/apps raise
  NotImplementedError until P2/P4) + `get_backend()` singleton
- Wired `common/python/capture/__init__.py` Linux branch → `backend.capture.CaptureStrategyFactory`
- **Verified on this machine:** full-screen capture 2560x1440 non-black ✓; window crop 2468x1398
  non-black ✓; active window + 8 windows + monitor geometry parsed ✓

**Windows ref:** `dxcam_capture.py` (strategy pattern) + `capture/__init__.py:46-74` (dispatch)

### Phase 2 — Physical input (Rust) — unlocks autopilot clicking ✅ DONE
- **KEY FINDING:** ydotool's `--absolute` is **software-emulated** (virtual device is REL-only,
  no ABS axes) and drifts badly on real compositors — large jumps get ~1.8×-scaled by libinput
  pointer acceleration. REL-based positioning is only exact for small deltas.
- **Hyprland 0.56 dispatcher rework:** old `hyprctl dispatch movecursor x y` is GONE (Lua-ified).
  Replacement: `hyprctl eval 'hl.dispatch(hl.dsp.cursor.move({ x, y }))'` — verified **pixel-exact**
  (100,100 → 100,100; 640,360 → 640,360).
- `backend/input.py`: compositor-agnostic injection —
  - `move_to(x,y)` → `hl.dsp.cursor.move` (the ONLY compositor-dependent piece; GNOME/KDE plug their own later)
  - `click` → `ydotool click 0xC0/0xC1/0xC2` (uinput, universal)
  - `scroll` → `ydotool mousemove -w -- dx dy` (REL_WHEEL/HWHEEL)
  - `key` → media via `ydotool key 0xA3/0xA4/0xA5/0x71-0x73`; combos via `wtype -M`
  - `type_text` → `wtype`; `focus_window` → hyprctl dispatch focuswindow
- `linux.rs` (Rust): click/scroll/type now spawn the same binaries directly (no Python hop for
  the Tauri command surface). `cargo check` + 12/12 tests pass.
- **Verified live:** click at (500,400) → cursor (500,400) ✓; (1500,900) ✓; scroll+wheel ✓;
  media key ✓; wtype ✓
- **Windows parity ref:** `windows.rs:15-53` (SendInput) → linux.rs (hyprctl+ydotool)

### Phase 3 — Screen semantics: OCR + window identity ✅ DONE
- OCR: pytesseract already dispatched from `common/ocr/__init__.py` on Linux (tesseract 5.5.2 + eng
  data installed). **376-449 items/screenshot** in ~1.8s, coords in screenshot space (same shape as
  Windows WinRT OCR — `attach_matches`/frontend unchanged).
- Window identity: `utils/window.py` `_get_active_window_linux()` re-pointed to
  `backend.window.get_active_window()` (hyprctl) with legacy KWin chain as fallback until P7.
  `get_target_window_element()` now returns a `_LinuxWindowAdapter` (exposes `.process_id()` so
  main.py's PID-lock contract works unchanged).
- **Verified live:** full `observe_app_state` pipeline — active window detected (Hermes, 4ms),
  372 OCR items with coords; locator fast-path matched "new session" @0.909 → step with
  `target_ref=@e3` (exact Windows tutor flow, no LLM needed).
- **Windows ref:** `winrt_ocr.py` → pytesseract; `uia.py` → OCR-only for now (AT-SPI in P8)

### Phase 4 — Direct actions (Python tools) — port `tools_win.py` one fn at a time
| tools_win.py fn | Hyprland equivalent |
|---|---|
| `open_app_tool_impl` (protocol→known_path→start_apps→search) | `open_app_tool_linux` exists — add hyprctl/gio launch + .desktop scan; flatpak detection |
| `shortcut_tool_impl` (pywinauto send_keys + VK media codes) | **NEW** `linux/backend/input.py` media keys via ydotool keycodes (KEY_PLAYPAUSE 0xCF etc.) |
| `find_start_app_impl` (Get-StartApps) | `app_inventory.py` `_kde_apps/_gnome_apps` + `hyprctl clients` running set |
| `open_app_via_windows_search_impl` (Win+S type) | not needed: `.desktop` scan replaces search |
| `find_windows_search_result_impl` (UIA match) | drop — search-launch is direct on Linux |
| `click_item_center` (pywinauto.mouse) | `backend/input.py` ydotool click at center |
- Update `shortcut_tool()` dispatch in tools.py (currently ImportError → "Windows only")
- Media playback (play_spotify/play_youtube/seek) already platform-neutral via webbrowser/DBus? —
  **check spotify seek path** (tools.py seek_spotify_tool) — port if it shells out
- **Verify:** "open firefox", "press ctrl+s", "next song", "volume up"

### Phase 5 — Autopilot loop rewrite (`loop.py` calls) ✅ DONE
- `linux_mcp.py` is now a **re-export shim** over `backend/linux_mcp_compat.py` — same function
  names/signatures (list_windows, list_apps, get_app_state, click_element, type_text, press_key,
  screenshot, get_focused_window_bounds, doctor, get_client, _check_ok) implemented over
  HyprlandBackend. **Zero caller changes** in tools.py/loop.py.
- Compat maps pywinauto-style media names (`media_play_pause` → `play`) to backend vocabulary.
- `get_app_state` returns windows + empty element tree (no AT-SPI on Hyprland; P8 adds it).
- **Verified live:** list_windows 14 ✓; click_element(x,y) ✓; press_key media ✓; screenshot_tool
  (grim+OCR, 359 items) ✓; `_get_fresh_window_bounds` (1228x1398 real geometry) ✓; full
  `run_computer_use_loop` with Ollama gemma4:e2b — LLM planned, list_windows executed ×2 ✓
  (loop quirk: gemma4 called a nonexistent "answer" tool — pre-existing, not a port issue)

### Phase 6 — Power + volume ✅ DONE
- `power.rs` updated: pactl-only volume (dropped amixer — ALSA-only), hyprctl lock → loginctl →
  DE fallbacks, grim screenshot first (headless, prompt-free) → gnome-screenshot/spectacle.
- `cargo check` clean; live pactl +5%/-5% round-trip verified (100% → 105% → 100%).

### Phase 7 — Cleanup + tests ✅ DONE
- **Deleted:** `mcp_bridge.rs` (+ `mod mcp_bridge` in lib.rs), `linux/python/window_linux.py`,
  `wayland_vision.py` (old), `linux_capture.py` (old).
- **Replaced with shims (same signatures, backend-backed):** `computer_use/linux_mcp.py` →
  `backend/linux_mcp_compat.py`; `linux/python/wayland_vision.py` → `backend/vision.py`
  (hyprctl scale, grim crop, translate_to_absolute, click_at_absolute).
- `utils/window.py` fallback chain re-pointed to backend.vision.
- **Tests: 235 passed** (up from 227 pre-port); 10 remaining failures are pre-existing
  env/LLM/network deps (identical set, verified). `test_virtual_mouse` (6 tests) and
  `test_browser_agent` now **pass** — fixed by the port.
- Rust: cargo check clean, 12/12 tests pass.

### Phase 8 — GNOME → KDE backends (same ABC, different window source)
- `gnome.py`: window bounds via XDG portal / X11 fallback (xdotool when XWayland); capture via portal;
  input: ydotool still works (uinput is compositor-agnostic) — **ydotool is the win here**
- `kde.py`: KWin via `kwin_script` DBus or `qdbus` for active window; capture via grim/KWin;
  AT-SPI for element trees (pyatspi)
- **Verify on each DE:** capture → guidance → autopilot → power

---

## Reference: what to port (Windows → Hyprland) — complete map

| # | Windows component | Ported by phase | Hyprland target |
|---|---|---|---|
| 1 | `dxcam_capture.py` DXCam strategy | P1 | grim + portal strategies |
| 2 | `winrt_ocr.py` | P3 | pytesseract (already in common/ocr) |
| 3 | `uia.py` get_visible_ui_text | P3(+P8) | OCR-only now; AT-SPI later |
| 4 | `window.py` target-window scan | P3 | hyprctl activewindow/clients |
| 5 | `windows.rs` click/scroll/type (SendInput) | P2 | linux.rs → ydotool/wtype |
| 6 | `windows.rs` global click listener | P2 | no-op (overlay passthrough OK) |
| 7 | `power.rs` (Windows) | P6 | linux power.rs exists, +hyprctl lock, pactl |
| 8 | `tools_win.py` open_app_tool_impl | P4 | open_app_tool_linux + .desktop scan |
| 9 | `tools_win.py` shortcut_tool_impl | P4 | backend/input.py media keys |
| 10 | `tools_win.py` find_start_app_impl | P4 | app_inventory + hyprctl clients |
| 11 | `tools_win.py` windows-search fns | P4 | drop (direct launch) |
| 12 | `loop.py` linux_mcp calls | P5 | backend ABC |
| 13 | `mcp_bridge.rs` | P7 | DELETE |
| 14 | `linux_mcp.py` | P7 | DELETE |

## Hyprland-specific notes
- **ydotool needs root/uinput:** either `sudo systemctl enable --now ydotool` or add user to
  `input` group + udev rule. Verify before P2.
- **Coordinates:** Hyprland global monitors — use `hyprctl monitors -j` for per-monitor origin +
  scale (ydotool uses absolute device coords; multiply by scale).
- **wtype for typing** (wlroots-native, works on Hyprland). Install in P0.
- **grim full-screen** works w/o portal prompts on Hyprland (wlroots). Portal is fallback.
- **No AT-SPI on Hyprland by default** → element trees come later (P8 GNOME/KDE); OCR +
  UI-map cache is the Hyprland element story (already how `observe_app_state` can degrade).

---

## Appendix A — Backend ABC method signatures (adopted contract, Blinky-flavored)

Source contract: `~/.hermes/hermes-agent/tools/computer_use/backend.py`. Blinky keeps the
**shape** but trims cua-specific baggage (element_token, delivery_mode ladder) and adds
Blinky-specific needs (Screenshot dataclass parity, window bounds).

```python
# linux/python/backend/abc.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Core dataclasses ───────────────────────────────────────────────

@dataclass
class UIElement:
    """One interactable element on screen (OCR box or AT-SPI node)."""
    text: str                      # visible text / accessible name
    x: int                         # screen-absolute logical px (top-left)
    y: int
    width: int
    height: int
    source: str = "ocr"            # "ocr" | "atspi" | "uia" (parity w/ Windows items)
    role: str = ""                 # AT-SPI role (later); "" for OCR
    automation_id: str = ""        # stable id when available
    confidence: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

@dataclass
class Screenshot:
    """Mirror of common/python/capture/__init__.py::Screenshot — byte-compatible."""
    path: Path
    width: int
    height: int
    screen_width: int
    screen_height: int

@dataclass
class WindowInfo:
    """Normalized window descriptor (Windows `active_app` parity)."""
    title: str
    process: str                   # app_id class (e.g. "foot", "vivaldi-stable")
    supported: bool = True
    x: int = 0                     # window bounds, screen-absolute logical px
    y: int = 0
    width: int = 0
    height: int = 0
    pid: int | None = None
    window_id: str = ""            # hyprctl address (e.g. "0x563b521a4b70")

@dataclass
class ActionResult:
    ok: bool
    action: str                    # "click" | "type_text" | "key" | "scroll" | "open_app" ...
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

# ── Backend interface ──────────────────────────────────────────────

class ComputerUseBackend(ABC):
    """Linux desktop automation backend. One impl per compositor:
    HyprlandBackend (P0-P5), GnomeBackend (P8), KdeBackend (P8)."""

    # ── Lifecycle ──────────────────────────────────────────────
    @abstractmethod
    def start(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def is_available(self) -> bool: ...

    # ── Screen ──────────────────────────────────────────────────
    @abstractmethod
    def capture(self, *, window: bool = False) -> Screenshot:
        """Full screen (window=False) or active-window crop (window=True)."""

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """(width, height) of the physical display in logical px."""

    # ── Windows / apps ──────────────────────────────────────────
    @abstractmethod
    def get_active_window(self) -> WindowInfo | None: ...

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]: ...

    @abstractmethod
    def list_apps(self) -> list[dict[str, Any]]:
        """Installed apps: [{name, desktop_id, exec, startup_wm_class, source}]
        source ∈ {"native", "flatpak", "user", "snap"}."""

    @abstractmethod
    def launch_app(self, app_name: str) -> ActionResult:
        """.desktop scan → gio launch (flatpak handled by Exec line)."""

    # ── Input ───────────────────────────────────────────────────
    @abstractmethod
    def click(self, *, x: int, y: int, button: str = "left",
              click_count: int = 1) -> ActionResult: ...

    @abstractmethod
    def scroll(self, *, direction: str, amount: int = 3,
               x: int | None = None, y: int | None = None) -> ActionResult: ...

    @abstractmethod
    def type_text(self, text: str) -> ActionResult: ...

    @abstractmethod
    def key(self, keys: str) -> ActionResult:
        """Combo like 'ctrl+s' or media keys 'play', 'next', 'prev'."""

    @abstractmethod
    def focus_window(self, window_id: str) -> ActionResult: ...
```

### HyprlandBackend impl map (what each method calls)

| Method | Implementation |
|---|---|
| `start/stop/is_available` | check `ydotool` daemon socket + `grim` + `wtype` + `hyprctl` presence |
| `capture(window=False)` | `grim -o <monitor> out.png`; `window=True` → `hyprctl activewindow -j` bounds → `grim -g "x,y WxH"` |
| `screen_size` | `hyprctl monitors -j` (max x+width, y+height; multiply by scale) |
| `get_active_window` | `hyprctl activewindow -j` → WindowInfo |
| `list_windows` | `hyprctl clients -j` → [WindowInfo] (filter mapped+visible) |
| `list_apps` | scan 3 .desktop dirs (user > flatpak exports > system); parse Name/Exec/StartupWMClass |
| `launch_app` | find .desktop by Name or stem → `gio launch <file>`; fallback binary_map → `hyprctl dispatch exec` |
| `click` | `ydotool mousemove --absolute x y` + `ydotool click 0xC0` (scale-aware) |
| `scroll` | `ydotool mousemove` + `ydotool click --repeat N 0x08/0x09` (wheel) |
| `type_text` | `wtype -s <rate> "<text>"` |
| `key` | combos: `wtype -M ctrl s -m ctrl`; media: `ydotool key 0xA4/0xA3/0xA5` |
| `focus_window` | `hyprctl dispatch focuswindow address:<id>` |

### P0 environment checklist (this machine)
- [ ] `sudo pacman -S tesseract tesseract-data-eng`  ← Arch name (NOT tesseract-ocr)
- [ ] wtype ✓ (already installed)
- [ ] ydotool daemon: **no systemd unit on Arch** — either:
      `sudo systemctl edit --force --full ydotool.service` (Type=simple, ExecStart=/usr/bin/ydotool)
      or run `ydotool` in background with `sudo` once / add udev rule + input group
- [ ] verify: `ydotool click 0xC0` moves/click mouse
- [ ] verify: `grim out.png` produces non-black full-screen shot
- [ ] verify: `wtype "hi"` types into a focused text field
