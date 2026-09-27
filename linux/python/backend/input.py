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

import os
import shutil
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


def _hyprctl_run(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
    """Run hyprctl with the resolved current instance (survives DE restarts)."""
    from .window import _current_instance_sig

    env = os.environ.copy()
    sig = _current_instance_sig()
    if sig:
        env["HYPRLAND_INSTANCE_SIGNATURE"] = sig
    return subprocess.run(
        ["hyprctl", *args], capture_output=True, text=True, timeout=timeout, env=env
    )


def _cursor_pos() -> tuple[int, int]:
    """Current cursor position in logical px (compositor-specific source).

    Routed through the active backend's cursor source (hyprctl on Hyprland,
    xdotool on X11/XWayland). Falls back to a best-effort hyprctl attempt.
    """
    try:
        # X11/XWayland → xdotool is the compositor-agnostic source
        if shutil.which("xdotool"):
            result = subprocess.run(
                ["xdotool", "getmouselocation", "--shell"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                vals = dict(
                    line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
                )
                if "X" in vals and "Y" in vals:
                    return int(vals["X"]), int(vals["Y"])
    except Exception as exc:
        LOGGER.debug("cursorpos xdotool failed: %s", exc)

    try:
        result = _hyprctl_run(["cursorpos"])
        if result.returncode == 0:
            x_str, y_str = result.stdout.strip().split(",")
            return int(x_str.strip()), int(y_str.strip())
    except Exception as exc:
        LOGGER.debug("cursorpos query failed: %s", exc)
    raise InputError("Could not determine cursor position")


def move_to(x: int, y: int) -> None:
    """Move the pointer to absolute (x, y).

    Per-compositor, per availability:
      1. Hyprland → native compositor dispatcher (pixel-exact, immune to accel)
      2. Non-Hyprland X11/XWayland → xdotool mousemove (pixel-exact; GNOME/KDE
         XWayland syncs the X pointer to the Wayland cursor)
      3. Otherwise (pure Wayland, no X) → ydotool relative emulation with a
         compensation constant; imperfect for large jumps but functional.
    """
    from .window import _is_hyprland

    # 1. Hyprland native dispatcher (pixel-exact, immune to accel). MUST be
    #    checked before xdotool — Hyprland's XWayland pointer does NOT sync to
    #    the Wayland cursor, so xdotool would move the wrong pointer.
    if _is_hyprland() and shutil.which("hyprctl"):
        script = f"hl.dispatch(hl.dsp.cursor.move({{ x = {int(x)}, y = {int(y)} }}))"
        try:
            result = _hyprctl_run(["eval", script])
            if result.returncode == 0:
                return
        except Exception as exc:
            LOGGER.debug("hyprctl cursor move failed: %s", exc)

    # 2. X11/XWayland: xdotool is pixel-exact and works on GNOME/KDE/X11
    if not _is_hyprland() and shutil.which("xdotool") and os.environ.get("DISPLAY"):
        try:
            result = subprocess.run(
                ["xdotool", "mousemove", str(int(x)), str(int(y))],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return
        except Exception as exc:
            LOGGER.debug("xdotool mousemove failed: %s", exc)

    # 3. Pure-Wayland fallback: ydotool REL emulation with accel compensation.
    #    ydotool's virtual device is REL-only, so absolute positions are
    #    software-emulated. We compute the delta from the current cursor.
    try:
        cx, cy = _cursor_pos()
        dx, dy = int(x) - cx, int(y) - cy
        # Compensate the ~1.8× libinput pointer-accel scaling observed on real
        # compositors for large jumps.
        if abs(dx) > 10 or abs(dy) > 10:
            dx = int(round(dx * 0.55))
            dy = int(round(dy * 0.55))
        _run(["ydotool", "mousemove", "--", str(dx), str(dy)])
    except InputError as exc:
        raise InputError(f"Could not move cursor: {exc}")


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
    """Type text. wtype first (wlroots-native); ydotool type fallback (uinput,
    works on any compositor — GNOME/KDE don't expose the virtual-keyboard
    protocol wtype needs)."""
    if not text:
        return ActionResult(True, "type_text", "Nothing to type")
    try:
        _run(["wtype", text])
        return ActionResult(True, "type_text", f"Typed {len(text)} chars")
    except InputError:
        pass  # wtype unsupported (e.g. GNOME) — fall through to ydotool
    try:
        # uinput-based; compositor-agnostic
        _run(["ydotool", "type", "--", text])
        return ActionResult(True, "type_text", f"Typed {len(text)} chars (ydotool)")
    except InputError as exc:
        return ActionResult(False, "type_text", str(exc))


# Linux input keycodes (input-event-codes.h) — QWERTY linear scan order.
# ydotool is uinput-only, so we translate common keys/aliases/modifiers
# ourselves (wtype's XKB names don't apply to ydotool's raw keycodes).
_YDOTOOL_KEYCODES = {
    "enter": 28, "return": 28,
    "esc": 1, "escape": 1,
    "tab": 15, "space": 57,
    "backspace": 14, "delete": 111, "del": 111,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
}
_MODIFIER_KEYCODES = {
    "ctrl": 29, "control": 29,
    "shift": 42,
    "rightshift": 54, "rightctrl": 97,
    "alt": 56, "meta": 125, "super": 125,
}
# QWERTY linear scan (Keycodes in input-event-codes.h, not alphabetical).
_ASCII_KEYCODES = {
    'q':16,'w':17,'e':18,'r':19,'t':20,'y':21,'u':22,'i':23,'o':24,'p':25,
    'a':30,'s':31,'d':32,'f':33,'g':34,'h':35,'j':36,'k':37,'l':38,
    'z':44,'x':45,'c':46,'v':47,'b':48,'n':49,'m':50,
    '1':2,'2':3,'3':4,'4':5,'5':6,'6':7,'7':8,'8':9,'9':10,'0':11,
    '-':12,'=':13,'[':26,']':27,';':39,"'":40,'`':41,'\\':43,',':51,'.':52,'/':53,
}


def _ydotool_keycode(name: str) -> int | None:
    """Resolve a single-character or named key to a ydotool keycode."""
    if name in _YDOTOOL_KEYCODES:
        return _YDOTOOL_KEYCODES[name]
    if name in _MODIFIER_KEYCODES:
        return _MODIFIER_KEYCODES[name]
    if len(name) == 1:
        ch = name.lower()
        if ch in _ASCII_KEYCODES:
            return _ASCII_KEYCODES[ch]
    return None


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

    parts = [p for p in key_lower.split("+") if p]

    # Try wtype first (wlroots-native, keeps Hyprland behavior identical)
    _ALIASES = {
        "enter": "Return", "return": "Return",
        "esc": "Escape", "escape": "Escape",
        "tab": "Tab", "space": "space",
        "backspace": "BackSpace", "delete": "Delete", "del": "Delete",
        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "home": "Home", "end": "End", "pageup": "Page_Up", "pagedown": "Page_Down",
    }
    try:
        if len(parts) < 2:
            single = _ALIASES.get(parts[0] if parts else key_lower, parts[0] if parts else key_lower)
            _run(["wtype", "-k", single])
            return ActionResult(True, "key", f"Pressed '{key_lower}'")
        mods, final_key = parts[:-1], parts[-1]
        final_key = _ALIASES.get(final_key, final_key)
        cmd = ["wtype"]
        for mod in mods:
            cmd += ["-M", mod]
        cmd.append(final_key)
        for mod in reversed(mods):
            cmd += ["-m", mod]
        _run(cmd)
        return ActionResult(True, "key", f"Pressed '{key_lower}'")
    except InputError:
        pass  # wtype unsupported (GNOME/etc.) — fall through to ydotool

    # ydotool fallback: raw keycode dance (uinput, compositor-agnostic).
    # Press all keys down together, release in reverse.
    try:
        if len(parts) < 2:
            code = _ydotool_keycode(parts[0] if parts else key_lower)
            if code is None:
                return ActionResult(False, "key", f"Unknown key '{key_lower}'")
            _run(["ydotool", "key", f"{code}:1", f"{code}:0"])
            return ActionResult(True, "key", f"Pressed '{key_lower}' (ydotool)")

        mods, final_key = parts[:-1], parts[-1]
        codes: list[int] = []
        for mod in mods:
            c = _MODIFIER_KEYCODES.get(mod)
            if c is None:
                return ActionResult(False, "key", f"Unknown modifier '{mod}'")
            codes.append(c)
        fin = _ydotool_keycode(final_key)
        if fin is None:
            return ActionResult(False, "key", f"Unknown key '{final_key}'")
        codes.append(fin)
        # down all, up all (reverse)
        events: list[str] = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
        _run(["ydotool", "key", *events])
        return ActionResult(True, "key", f"Pressed '{key_lower}' (ydotool)")
    except InputError as exc:
        return ActionResult(False, "key", str(exc))


def focus_window(window_id: str) -> ActionResult:
    """Focus a window by its backend-specific id.

    Per-compositor:
      - hyprctl address (Hyprland)
      - xdotool windowactivate (X11/XWayland)
      - XDG portal ActivateWindow (GNOME/KDE, gives focus without raising)
    Contacts multiple strategies; returns the first success.
    """
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    # 1. Hyprland
    if "hypr" in de and window_id.startswith("0x"):
        try:
            _run(["hyprctl", "dispatch", "focuswindow", f"address:{window_id}"])
            return ActionResult(True, "focus_window", f"Focused {window_id}")
        except InputError:
            pass

    # 2. X11/XWayland
    if shutil.which("xdotool"):
        try:
            _run(["xdotool", "windowactivate", "--sync", window_id])
            return ActionResult(True, "focus_window", f"Focused X window {window_id}")
        except InputError:
            pass

    # 3. Portal ActivateWindow (compositor-agnostic; GNOME/KDE/any Wayland)
    try:
        from .portal import activate_window

        if activate_window(window_id):
            return ActionResult(True, "focus_window", f"Focused {window_id} via portal")
    except Exception as exc:
        LOGGER.debug("portal activate_window failed: %s", exc)

    return ActionResult(False, "focus_window", f"Cannot focus {window_id}")
