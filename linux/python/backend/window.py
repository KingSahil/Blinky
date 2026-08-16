"""Hyprland window introspection via `hyprctl`.

Replaces the KWin/xdotool/xprop chains in the old window_linux.py with the
Hyprland-native IPC source. All commands return JSON (`-j`) which we parse
into WindowInfo.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from utils.logging import get_logger

from .abc import WindowInfo

LOGGER = get_logger("blinky.backend.window")

HYPRCTL = "hyprctl"

# Processes the overlay/tutor itself should never treat as the "active app".
IGNORED_PROCESS_HINTS = ("blinky", "tauri", "cae", "waybar", "rofi", "wofi")


def _run_hyprctl(args: list[str], timeout: float = 5.0) -> Any | None:
    try:
        result = subprocess.run(
            [HYPRCTL, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            LOGGER.debug("hyprctl %s failed: %s", args, result.stderr.strip())
            return None
        return json.loads(result.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        LOGGER.debug("hyprctl %s error: %s", args, exc)
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


def get_active_window() -> WindowInfo | None:
    """Active/focused window via `hyprctl activewindow -j`."""
    data = _run_hyprctl(["activewindow", "-j"])
    if not isinstance(data, dict) or data.get("mapped") is False:
        return None
    return _window_info_from_client(data)


def list_windows() -> list[WindowInfo]:
    """All mapped, visible windows via `hyprctl clients -j`."""
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
