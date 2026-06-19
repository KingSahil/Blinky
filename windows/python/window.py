from __future__ import annotations

import os
import psutil
from utils.logging import get_logger

LOGGER = get_logger("blinky.window")

IGNORED_OVERLAY_PROCESSES = {
    "snippingtool.exe",
}

IGNORED_OVERLAY_TITLE_HINTS = {
    "recording toolbar",
}


def _is_ignored_overlay_window(process_name: str, title: str) -> bool:
    name_lower = process_name.lower().strip()
    title_lower = title.lower().strip()
    return name_lower in IGNORED_OVERLAY_PROCESSES or any(hint in title_lower for hint in IGNORED_OVERLAY_TITLE_HINTS)


def _get_target_window_element_impl(window=None, target_pid: int | None = None):
    if os.name != "nt":
        return None

    if window is not None:
        return window

    try:
        from pywinauto import Desktop

        windows = Desktop(backend="uia").windows()
        for w in windows:
            try:
                if not w.is_visible():
                    continue
                title = w.window_text()
                if not title or not title.strip():
                    continue

                process_id = w.process_id()

                if target_pid is not None and process_id != target_pid:
                    continue

                process_name = psutil.Process(process_id).name().lower()

                if "blinky" in process_name or "tauri" in process_name or "blinky" in title.lower():
                    continue

                if _is_ignored_overlay_window(process_name, title):
                    LOGGER.info("Ignoring overlay window while selecting target: %s (%s)", title, process_name)
                    continue

                if process_name in {
                    "searchhost.exe",
                    "shellexperiencehost.exe",
                    "startmenuexperiencehost.exe",
                    "lockapp.exe",
                    "systemsettings.exe"
                }:
                    continue

                if title in {"Taskbar", "Program Manager", "Settings", "Action Center"}:
                    continue

                if process_name == "explorer.exe" and title in {"Taskbar", "Program Manager", "FolderView"}:
                    continue

                LOGGER.info("Detected target application window: %s (%s)", title, process_name)
                return w
            except Exception:
                continue
    except Exception as exc:
        LOGGER.warning("Failed to scan Z-order windows: %s", exc)

    try:
        from pywinauto import Desktop
        active = Desktop(backend="uia").get_active()
        process_name = psutil.Process(active.process_id()).name().lower()
        title = active.window_text()
        if _is_ignored_overlay_window(process_name, title):
            LOGGER.info("Ignoring active overlay fallback window: %s (%s)", title, process_name)
            return None
        return active
    except Exception:
        return None


def get_target_window_element(window=None, target_pid: int | None = None):
    return _get_target_window_element_impl(window, target_pid)
