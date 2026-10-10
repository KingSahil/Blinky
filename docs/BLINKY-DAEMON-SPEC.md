# Blinky Daemon Specification & Final Architecture

## 1. System Overview

`blinky-daemon` is a headless, high-performance, asynchronous Linux desktop automation and semantic information extraction service written in Rust. It runs inside the user's active graphical session (managed via `systemd --user` or background process) and exposes a line-delimited JSON-RPC 2.0 interface over a local UNIX domain socket at `$XDG_RUNTIME_DIR/blinky-daemon.sock`.

Its primary responsibility is to provide **100% deterministic, grounded ground truth** to the Blinky desktop client, Python AI orchestrator, and external agents for:
1. Application discovery & execution
2. Monitor geometry & multi-display topology
3. Active and background window bounding boxes, PIDs, and workspace mapping
4. High-speed headless & interactive screen/window captures (returning on-disk image paths)
5. Pixel-exact cursor movement, virtual mouse clicking, scrolling, and keyboard typing
6. Accessibility tree (AT-SPI2) semantic node traversal
7. System session (power, sleep, lock) and media (MPRIS) control

---

## 2. Universal vs. Compositor-Specific Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       blinky-daemon                                         │
│                      (Headless User Session Service / IPC Server)                          │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                  UNIVERSAL SUBSYSTEMS                                       │
│  ┌───────────────────────┬──────────────────────┬────────────────────┬───────────────────┐  │
│  │ XDG Desktop Registry  │     AT-SPI2 D-Bus    │    MPRIS2 D-Bus    │  systemd logind   │  │
│  │ (.desktop parser/gio) │  (Accessibility Tree)│ (Media Playback)   │ (Power & Session) │  │
│  ├───────────────────────┼──────────────────────┼────────────────────┼───────────────────┤  │
│  │ PulseAudio / PipeWire │   Linux /dev/uinput  │ XDG Desktop Portal │   Tesseract OCR   │  │
│  │ (Volume/Sink Control) │ (Kernel Input Subsys)│(ScreenCast/Fallback│  (Neural Vision)  │  │
│  └───────────────────────┴──────────────────────┴────────────────────┴───────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                             COMPOSITOR-SPECIFIC ADAPTERS                                    │
│  ┌───────────────────────┬──────────────────────┬────────────────────┬───────────────────┐  │
│  │   Hyprland Adapter    │    GNOME (Mutter)    │  KDE Plasma (KWin) │  Sway / wlroots   │  │
│  │ - UNIX socket IPC     │ - Shell.Introspect   │ - KWin Scripting   │ - Sway IPC socket │  │
│  │ - Event stream (sock2)│ - Mutter ScreenCast  │ - Plasma Window Mgmt- wlr-screencopy   │  │
│  │ - hl.dsp.cursor.move  │ - AT-SPI window map  │ - KWin DBus Ping   │ - wlr-virtual-kb  │  │
│  └───────────────────────┴──────────────────────┴────────────────────┴───────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Breakdown & Wire Protocols

### A. Window Introspection & Geometry Tracking
- **Hyprland:** Direct UNIX domain socket at `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock`.
  - Commands: `j/activewindow`, `j/clients`, `j/monitors`, `j/workspaces`, `j/cursorpos`.
  - Event Stream: `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock` (`activewindow>>`, `openwindow>>`, `closewindow>>`, `monitoradded>>`, `monitorremoved>>`).
- **KDE Plasma (KWin):** Session D-Bus `org.kde.KWin.Scripting` via `loadScript` & `run`.
- **GNOME Shell (Mutter):** Session D-Bus `org.gnome.Shell.Introspect` method `GetWindows()`.
- **Sway / Generic wlroots:** UNIX domain socket `$SWAYSOCK` using `swaymsg -t get_tree`.
- **X11 / XWayland Fallback:** X11 XCB client queries (`_NET_CLIENT_LIST`, `_NET_ACTIVE_WINDOW`).

### B. Coordinate Transformation Matrix
- **Logical Space:** The compositor's coordinate system (e.g. 2560x1440 at logical offset (0,0)).
- **Physical Space:** The raster framebuffer space (e.g. scaled display 3840x2160 at scale 1.5).
- **Transformation Formula:**
  $$\text{Physical Coordinates} = (\text{Logical Coordinates} - \text{Monitor Logical Origin}) \times \text{Monitor Scale}$$
  $$\text{Logical Coordinates} = \frac{\text{Physical Coordinates}}{\text{Monitor Scale}} + \text{Monitor Logical Origin}$$
- **Monitor Topology:** Sourced dynamically from compositor monitor queries and kept fresh via compositor event streams.

### C. Screen Capture Engine
- **Headless Fullscreen:** `grim` via `wlr-screencopy-unstable-v1` capturing per-monitor outputs (`-o <name>`) and stitching in geometry order.
- **Headless Window Crop:** Bounding box capture using `grim -g "<x>,<y> <w>x<h>"`.
- **Interactive Screenshot:** Spawns `slurp` for interactive user ROI selection piped directly into `grim`.
- **Portal Fallback:** `org.freedesktop.portal.Screenshot` on D-Bus session bus.
- **Caching Contract:** Saves optimized JPEG/PNG files under `~/.cache/blinky/captures/` and returns absolute file paths over IPC.

### D. Input Subsystem
- **Cursor Positioning:**
  - Hyprland: `hl.dispatch(hl.dsp.cursor.move({ x = X, y = Y }))` via compositor dispatcher (immune to pointer acceleration).
  - Generic Wayland/X11: `uinput` relative displacement or `xdotool mousemove`.
- **Mouse Clicks & Wheel Scrolling:** Direct Linux `/dev/uinput` virtual device injection emitting `EV_KEY` (`BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE`) and `EV_REL` (`REL_WHEEL`, `REL_HWHEEL`).
- **Keyboard Typing & Combinations:** `wtype` (wlroots virtual keyboard protocol) and `/dev/uinput` raw keycode sequences.

### E. Universal App Registry
- Parses `.desktop` files across standard XDG paths:
  1. `~/.local/share/applications` (User & user-flatpak)
  2. `/var/lib/flatpak/exports/share/applications` (System flatpaks)
  3. `/usr/local/share/applications` (Local builds)
  4. `/usr/share/applications` (System packages)
- Extracts `Name`, `Exec`, `StartupWMClass`, `Icon`, `Categories`, `NoDisplay`.
- Launches via `gio launch <path.desktop>` or direct sanitized `Exec` process spawning.

### F. Accessibility Tree (AT-SPI2)
- Queries `org.a11y.Bus` at `/org/a11y/bus` $\rightarrow$ `GetAddress()`.
- Walks `org.a11y.atspi.Registry` to extract `UIElement` bounds, accessible names, roles, and focus states.

### G. Media, Audio & Power
- **Media Control:** D-Bus `org.mpris.MediaPlayer2.*` (`Play`, `Pause`, `PlayPause`, `Next`, `Previous`, `Seek`, `Metadata`).
- **Volume:** Native PulseAudio/PipeWire protocol (`/run/user/$UID/pulse/native`).
- **Power & Session:** System D-Bus `org.freedesktop.login1.Manager` (`PowerOff`, `Reboot`, `Suspend`, `Hibernate`, `LockSession`).

---

## 4. IPC JSON-RPC 2.0 Interface Specification

### Socket Location
`$XDG_RUNTIME_DIR/blinky-daemon.sock` (mode `0600`)

### Methods
1. `blinky.getSystemInfo` $\rightarrow$ Compositor name, session type, DE profile, toolchain presence.
2. `blinky.getMonitors` $\rightarrow$ List of active monitors with logical bounds, physical resolutions, scale factors, and refresh rates.
3. `blinky.getWindows` $\rightarrow$ List of mapped windows with address, title, class, PID, and global logical bounds.
4. `blinky.getActiveWindow` $\rightarrow$ Active window details or `null`.
5. `blinky.getApps` $\rightarrow$ Complete installed application catalog.
6. `blinky.launchApp` $\rightarrow$ `{ "name": "...", "desktop_id": "..." }`.
7. `blinky.captureScreen` $\rightarrow$ `{ "monitor": "...", "all": true }` $\rightarrow$ Returns `{ "path": "/...", "width": ..., "height": ... }`.
8. `blinky.captureWindow` $\rightarrow$ `{ "window_id": "..." }` $\rightarrow$ Returns `{ "path": "/...", "bounds": { ... } }`.
9. `blinky.captureInteractive` $\rightarrow$ User drags a region with `slurp` $\rightarrow$ Returns `{ "path": "/...", "bounds": { ... } }`.
10. `blinky.mouseMove` $\rightarrow$ `{ "x": ..., "y": ... }`.
11. `blinky.mouseClick` $\rightarrow$ `{ "x": ..., "y": ..., "button": "left|right|middle", "click_count": 1 }`.
12. `blinky.mouseScroll` $\rightarrow$ `{ "direction": "up|down|left|right", "amount": 3, "x": ..., "y": ... }`.
13. `blinky.keyboardType` $\rightarrow$ `{ "text": "..." }`.
14. `blinky.keyboardKey` $\rightarrow$ `{ "keys": "ctrl+shift+s|Return|..." }`.
15. `blinky.mediaControl` $\rightarrow$ `{ "command": "play_pause|next|prev|volume_up|volume_down|mute" }`.
16. `blinky.sessionControl` $\rightarrow$ `{ "command": "lock|suspend|hibernate|reboot|poweroff" }`.
