from __future__ import annotations

import os
import psutil
from utils.logging import get_logger

LOGGER = get_logger("blinky.window")

SUPPORTED_PROCESSES = {
    "code.exe",
    "code",
    "chrome.exe",
    "chrome",
    "google-chrome",
    "google-chrome.exe",
    "mspaint.exe",
    "mspaint",
    "explorer.exe",
    "explorer",
    "antigravity ide.exe",
    "antigravity-ide.exe",
    "antigravity ide",
    "antigravity-ide",
}

IGNORED_OVERLAY_PROCESSES = {
    "snippingtool.exe",
    "nvidia overlay.exe",
    "nvidiaoverlay.exe",
    "trae.exe",
    "blinky.exe",
    "nvsphelper64.exe",
    "nvcontainer.exe",
}

IGNORED_OVERLAY_TITLE_HINTS = {
    "recording toolbar",
    "blinky",
    "command",
    "overlay",
}


def is_process_supported(process_name: str) -> bool:
    name_lower = process_name.lower()
    if name_lower in SUPPORTED_PROCESSES:
        return True
    base_name = name_lower.rsplit('.', 1)[0]
    if base_name in SUPPORTED_PROCESSES:
        return True
    return False


def is_ignored_overlay_window(process_name: str, title: str) -> bool:
    name_lower = process_name.lower().strip()
    title_lower = title.lower().strip()
    return name_lower in IGNORED_OVERLAY_PROCESSES or any(hint in title_lower for hint in IGNORED_OVERLAY_TITLE_HINTS)


_local_ignored_rects: list[dict[str, int]] = []


def set_ignored_overlay_rects(rects: list[dict]) -> None:
    global _local_ignored_rects
    _local_ignored_rects = []
    if not rects:
        return
    for r in rects:
        if not isinstance(r, dict):
            continue
        x = r.get("x")
        y = r.get("y")
        w = r.get("width")
        h = r.get("height")
        if x is not None and y is not None and w is not None and h is not None:
            _local_ignored_rects.append({
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
            })


def get_ignored_overlay_rects() -> list[dict[str, int]]:
    if os.name != "nt":
        return _local_ignored_rects

    rects: list[dict[str, int]] = []
    try:
        from pywinauto import Desktop

        for w in Desktop(backend="uia").windows():
            try:
                if not w.is_visible():
                    continue
                title = w.window_text()
                process_name = psutil.Process(w.process_id()).name().lower()
                if not is_ignored_overlay_window(process_name, title):
                    continue
                rect = w.rectangle()
                rects.append(
                    {
                        "x": int(rect.left),
                        "y": int(rect.top),
                        "width": max(1, int(rect.width())),
                        "height": max(1, int(rect.height())),
                    }
                )
            except Exception:
                continue
    except Exception as exc:
        LOGGER.warning("Failed to scan ignored overlay windows: %s", exc)
    return rects


def get_target_window_element(window=None, target_pid: int | None = None):
    if os.name != "nt":
        return None
    try:
        from window import _get_target_window_element_impl
        return _get_target_window_element_impl(window, target_pid)
    except ImportError:
        return None


def get_active_window(window=None, target_pid: int | None = None) -> dict:
    if os.name == "nt":
        return _get_active_window_win(window, target_pid)
    else:
        return _get_active_window_linux()


def _get_active_window_win(window=None, target_pid: int | None = None) -> dict:
    try:
        from window import _get_target_window_element_impl
        w = _get_target_window_element_impl(window=window, target_pid=target_pid)
        if not w:
            raise RuntimeError("No active target window resolved.")

        process_id = w.process_id()
        process_name = psutil.Process(process_id).name()
        title = w.window_text()
        return {
            "title": title,
            "process": process_name,
            "supported": is_process_supported(process_name),
        }
    except Exception as exc:
        LOGGER.warning("Could not inspect active window on Windows: %s", exc)
        return {"title": "Unknown window", "process": "unknown", "supported": False}


def _get_active_window_linux() -> dict:
    try:
        from window_linux import get_active_window_linux
        return get_active_window_linux()
    except ImportError:
        pass

    session = os.environ.get("XDG_SESSION_TYPE", "wayland").lower()
    return {
        "title": "Linux Desktop",
        "process": session,
        "supported": False,
    }
