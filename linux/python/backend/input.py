"""Compositor-agnostic physical input via ydotool (uinput) + wtype.

Design (per roadmap decision): ydotool's virtual device is REL-only, so its
`--absolute` is software-emulated and drifts on real compositors. We instead
inject **relative** motions computed from the compositor's cursor position.
REL events are kernel-level (uinput) — identical on Hyprland, GNOME, KDE,
X11, and any compositor that accepts a standard pointer device.

The only compositor-dependent piece is *reading* the cursor position and
focused window (backend/window.py); injection here is 100% compositor-free.
"""

from __future__ import annotations

import subprocess
import time

from utils.logging import get_logger

from .abc import ActionResult
from .window import get_active_window

LOGGER = get_logger("blinky.backend.input")

# ydotool button codes (0x00 = left, 0x01 = right, 0x02 = middle; 0xC0 = left click)
_BUTTONS = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
_BUTTON_DOWN = {"left": "0x40", "right": "0x41", "middle": "0x42"}

# Linux input keycodes (input-event-codes.h) for media keys via ydotool key
_MEDIA_KEYCODES = {
    "play": "0xA4",        # KEY_PLAYPAUSE
    "pause": "0xA4",
    "play_pause": "0xA4",
    "next": "0xA3",        # KEY_NEXTSONG
    "prev": "0xA5",        # KEY_PREVIOUSSONG
    "previous": "0xA5",
    "stop": "0xA6",        # KEY_STOPCD
    "volume_up": "0x73",   # KEY_VOLUMEUP
    "volume_down": "0x72", # KEY_VOLUMEDOWN
    "mute": "0x71",        # KEY_MUTE
}


class InputError(Exception):
    pass


def _run(cmd: list[str], timeout: float = 5.0) -> None:
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise InputError(f"Tool not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise InputError(
            f"{cmd[0]} failed ({exc.returncode}): {exc.stderr.decode(errors='replace').strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise InputError(f"{cmd[0]} timed out") from exc


def _cursor_pos() -> tuple[int, int]:
    """Current cursor position in logical px (compositor-specific source)."""
    try:
        result = subprocess.run(
            ["hyprctl", "cursorpos"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            x_str, y_str = result.stdout.strip().split(",")
            return int(x_str.strip()), int(y_str.strip())
    except Exception as exc:
        LOGGER.debug("cursorpos query failed: %s", exc)
    raise InputError("Could not determine cursor position (hyprctl cursorpos)")


def move_to(x: int, y: int) -> None:
    """Move the pointer to absolute (x, y).

    Hyprland impl: native compositor dispatcher `hl.dsp.cursor.move` —
    pixel-exact, immune to libinput pointer acceleration (which corrupts
    ydotool's REL-based absolute emulation on large jumps).

    Compositor-agnostic note: this is the ONLY compositor-dependent piece of
    input. GNOME/KDE backends implement their own move_to (portal/xdotool);
    click/wheel/key injection below is pure uinput and works everywhere.
    """
    script = f"hl.dispatch(hl.dsp.cursor.move({{ x = {int(x)}, y = {int(y)} }}))"
    try:
        result = subprocess.run(
            ["hyprctl", "eval", script], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            raise InputError(f"hyprctl cursor move failed: {result.stderr.strip()}")
    except FileNotFoundError as exc:
        raise InputError("hyprctl not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise InputError("hyprctl cursor move timed out") from exc


def click(x: int, y: int, button: str = "left", click_count: int = 1) -> ActionResult:
    try:
        move_to(x, y)
        code = _BUTTONS.get(button, _BUTTONS["left"])
        for _ in range(max(1, click_count)):
            _run(["ydotool", "click", code])
            time.sleep(0.05)
        return ActionResult(True, "click", f"Clicked {button} at ({x}, {y})", {"x": x, "y": y})
    except InputError as exc:
        return ActionResult(False, "click", str(exc), {"x": x, "y": y})


def scroll(direction: str, amount: int = 3, x: int | None = None, y: int | None = None) -> ActionResult:
    """Scroll `amount` wheel ticks. direction ∈ up/down/left/right.
    Wheel deltas: up=+1, down=-1, left=+1, right=-1 (REL_WHEEL / REL_HWHEEL)."""
    try:
        if x is not None and y is not None:
            move_to(x, y)
        amount = max(1, min(amount, 20))
        if direction == "up":
            dx, dy = 0, amount
        elif direction == "down":
            dx, dy = 0, -amount
        elif direction == "left":
            dx, dy = -amount, 0
        elif direction == "right":
            dx, dy = amount, 0
        else:
            return ActionResult(False, "scroll", f"Unknown direction: {direction}")
        _run(["ydotool", "mousemove", "-w", "--", str(dx), str(dy)])
        return ActionResult(True, "scroll", f"Scrolled {direction} x{amount}")
    except InputError as exc:
        return ActionResult(False, "scroll", str(exc))


def type_text(text: str) -> ActionResult:
    """Type text via wtype (wlroots-native keyboard injection)."""
    if not text:
        return ActionResult(True, "type_text", "Nothing to type")
    try:
        _run(["wtype", text])
        return ActionResult(True, "type_text", f"Typed {len(text)} chars")
    except InputError as exc:
        return ActionResult(False, "type_text", str(exc))


def key(keys: str) -> ActionResult:
    """Send a key combo like 'ctrl+s' or a media key like 'play'/'next'."""
    key_lower = keys.strip().lower()

    # Media keys → ydotool key <keycode> (compositor-agnostic uinput)
    if key_lower in _MEDIA_KEYCODES:
        try:
            _run(["ydotool", "key", _MEDIA_KEYCODES[key_lower]])
            return ActionResult(True, "key", f"Pressed media key '{key_lower}'")
        except InputError as exc:
            return ActionResult(False, "key", str(exc))

    # Common aliases → wtype XKB key names. wtype does NOT know 'enter'/'esc'
    # (it wants 'Return'/'Escape') — without this, the LLM's natural vocabulary
    # fails and burns iterations.
    _ALIASES = {
        "enter": "Return",
        "return": "Return",
        "esc": "Escape",
        "escape": "Escape",
        "tab": "Tab",
        "space": "space",
        "backspace": "BackSpace",
        "delete": "Delete",
        "del": "Delete",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
        "pageup": "Page_Up",
        "pagedown": "Page_Down",
    }

    # Modifier combos → wtype: -M press mods, <key>, -m release mods
    parts = [p for p in key_lower.split("+") if p]
    if len(parts) < 2:
        # Single non-media key (e.g. "return", "escape") → wtype -k
        single = _ALIASES.get(parts[0] if parts else key_lower, parts[0] if parts else key_lower)
        try:
            _run(["wtype", "-k", single])
            return ActionResult(True, "key", f"Pressed '{key_lower}'")
        except InputError as exc:
            return ActionResult(False, "key", str(exc))

    mods, final_key = parts[:-1], parts[-1]
    final_key = _ALIASES.get(final_key, final_key)
    try:
        cmd = ["wtype"]
        for mod in mods:
            cmd += ["-M", mod]
        cmd.append(final_key)
        for mod in reversed(mods):
            cmd += ["-m", mod]
        _run(cmd)
        return ActionResult(True, "key", f"Pressed '{key_lower}'")
    except InputError as exc:
        return ActionResult(False, "key", str(exc))


def focus_window(window_id: str) -> ActionResult:
    """Focus a window via hyprctl dispatch (compositor-specific, Hyprland impl)."""
    try:
        _run(["hyprctl", "dispatch", "focuswindow", f"address:{window_id}"])
        return ActionResult(True, "focus_window", f"Focused {window_id}")
    except InputError as exc:
        return ActionResult(False, "focus_window", str(exc))
