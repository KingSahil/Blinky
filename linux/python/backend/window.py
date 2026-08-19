"""Hyprland window introspection via `hyprctl`.

Replaces the KWin/xdotool/xprop chains in the old window_linux.py with the
Hyprland-native IPC source. All commands return JSON (`-j`) which we parse
into WindowInfo.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from utils.logging import get_logger

from .abc import WindowInfo

LOGGER = get_logger("blinky.backend.window")

HYPRCTL = "hyprctl"

# Processes the overlay/tutor itself should never treat as the "active app".
IGNORED_PROCESS_HINTS = ("blinky", "tauri", "cae", "waybar", "rofi", "wofi")


def _current_instance_sig() -> str:
    """Resolve the ACTIVE Hyprland instance signature from the socket dir.

    hyprctl reads the HYPRLAND_INSTANCE_SIGNATURE env var; after a display-
    manager / session restart that env can be stale (points at a dead socket),
    which makes every hyprctl call silently fail — 0 windows, no monitor
    geometry, grim capture dead. Instead of trusting inherited env, scan
    $XDG_RUNTIME_DIR/hypr/ and pick the most recently created instance.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    hypr_dir = os.path.join(runtime, "hypr")
    try:
        entries = [
            d for d in os.listdir(hypr_dir)
            if os.path.isdir(os.path.join(hypr_dir, d)) and os.path.exists(
                os.path.join(hypr_dir, d, ".socket.sock")
            )
        ]
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        return ""
    if not entries:
        return ""
    if len(entries) == 1:
        return entries[0]
    # Prefer env var only when it is also the newest (avoids stale-socket pick)
    env_sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    entries.sort()
    newest = entries[-1]
    if env_sig == newest:
        return newest
    # Multiple instances: use the newest; callers retry on failure anyway
    return newest


def _run_hyprctl(args: list[str], timeout: float = 5.0) -> Any | None:
    """Run hyprctl, resolving the live instance; retry newest on connection fail.

    A stale HYPRLAND_INSTANCE_SIGNATURE makes hyprctl exit non-zero with a
    dead-socket connect error; when that happens with multiple instance dirs,
    retry once against the newest instance.
    """
    sig = _current_instance_sig()
    env = os.environ.copy()
    if sig:
        env["HYPRLAND_INSTANCE_SIGNATURE"] = sig

    def _call(sig_override: str | None) -> tuple[int, str]:
        run_env = env.copy()
        if sig_override:
            run_env["HYPRLAND_INSTANCE_SIGNATURE"] = sig_override
        try:
            result = subprocess.run(
                [HYPRCTL, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            LOGGER.debug("hyprctl %s error: %s", args, exc)
            return -1, ""
        return result.returncode, result.stdout

    rc, out = _call(None)
    if rc == 0:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None

    # Connection failure with multiple instances → retry newest
    newest = _current_instance_sig()
    if newest and newest != sig:
        LOGGER.debug("hyprctl retry against newest instance %s", newest)
        rc2, out2 = _call(newest)
        if rc2 == 0:
            try:
                return json.loads(out2)
            except json.JSONDecodeError:
                return None
    return None


def _is_ignored_process(process: str) -> bool:
    return any(hint in process.lower() for hint in IGNORED_PROCESS_HINTS)


def _window_info_from_client(client: dict[str, Any]) -> WindowInfo | None:
    """Convert one `hyprctl clients -j` entry into WindowInfo."""
    cls = str(client.get("class") or client.get("initialClass") or "")
    title = str(client.get("title") or "")
    if not cls and not title:
        return None
    if _is_ignored_process(cls) or _is_ignored_process(title):
        return None

    at = client.get("at") or [0, 0]
    size = client.get("size") or [0, 0]
    return WindowInfo(
        title=title,
        process=cls.split(".")[-1] if "." in cls else cls,
        supported=True,
        x=int(at[0]),
        y=int(at[1]),
        width=int(size[0]),
        height=int(size[1]),
        pid=client.get("pid"),
        window_id=str(client.get("address") or ""),
    )


def _is_hyprland() -> bool:
    """True when the ACTIVE session is a live Hyprland instance.

    Signals, in order of reliability:
      1. HYPRLAND_INSTANCE_SIGNATURE resolves to a live socket dir
      2. XDG_CURRENT_DESKTOP contains 'hypr'/'Hyprland' (the compositor's
         own advertisement)
    Tool binary presence (hyprctl installed) is NOT a signal — this machine
    has hyprctl even when booted into GNOME/KDE.
    """
    # 1. Live instance socket (most reliable — set by Hyprland into its session)
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if sig:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        if os.path.isdir(os.path.join(runtime, "hypr", sig)):
            return True

    # 2. DE advertisement
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "hypr" in de:
        return True

    return False


def _atspi_backend_windows() -> list[WindowInfo] | None:
    """AT-SPI window list when not on Hyprland. None = unavailable."""
    try:
        from .atspi import is_available, list_windows as atspi_list_windows

        if is_available():
            return atspi_list_windows()
    except Exception as exc:
        LOGGER.debug("AT-SPI window list unavailable: %s", exc)
    return None


def get_active_window() -> WindowInfo | None:
    """Active/focused window — compositor-aware (hyprctl or AT-SPI)."""
    if not _is_hyprland():
        try:
            from .atspi import get_active_window as atspi_active

            result = atspi_active()
            if result is not None:
                return result
        except Exception:
            pass
    data = _run_hyprctl(["activewindow", "-j"])
    if not isinstance(data, dict) or data.get("mapped") is False:
        return None
    return _window_info_from_client(data)


def list_windows() -> list[WindowInfo]:
    """All mapped, visible windows — compositor-aware (hyprctl or AT-SPI)."""
    if not _is_hyprland():
        atspi_windows = _atspi_backend_windows()
        if atspi_windows is not None:
            return atspi_windows
    data = _run_hyprctl(["clients", "-j"])
    if not isinstance(data, list):
        return []

    windows: list[WindowInfo] = []
    for client in data:
        if client.get("mapped") is False or client.get("hidden") is True:
            continue
        info = _window_info_from_client(client)
        if info is not None:
            windows.append(info)
    return windows


def get_monitors() -> list[dict[str, Any]]:
    """Monitor geometry via `hyprctl monitors -j` (name, x, y, width, height, scale)."""
    data = _run_hyprctl(["monitors", "-j"])
    if not isinstance(data, list):
        return []
    return [
        {
            "name": m.get("name", ""),
            "x": int(m.get("x", 0)),
            "y": int(m.get("y", 0)),
            "width": int(m.get("width", 0)),
            "height": int(m.get("height", 0)),
            "scale": float(m.get("scale", 1.0)),
        }
        for m in data
        if m.get("enabled", True)
    ]


def screen_size() -> tuple[int, int]:
    """Total virtual desktop size in logical px (max x+width, y+height)."""
    monitors = get_monitors()
    if not monitors:
        return 1920, 1080
    max_w = max(m["x"] + m["width"] for m in monitors)
    max_h = max(m["y"] + m["height"] for m in monitors)
    return max_w, max_h
