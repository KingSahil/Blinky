from __future__ import annotations

import os
import psutil
import subprocess
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
}

IGNORED_OVERLAY_TITLE_HINTS = {
    "recording toolbar",
}


def is_process_supported(process_name: str) -> bool:
    name_lower = process_name.lower()
    if name_lower in SUPPORTED_PROCESSES:
        return True
    # check extensionless name
    base_name = name_lower.rsplit('.', 1)[0]
    if base_name in SUPPORTED_PROCESSES:
        return True
    return False


def is_ignored_overlay_window(process_name: str, title: str) -> bool:
    name_lower = process_name.lower().strip()
    title_lower = title.lower().strip()
    return name_lower in IGNORED_OVERLAY_PROCESSES or any(hint in title_lower for hint in IGNORED_OVERLAY_TITLE_HINTS)


def get_ignored_overlay_rects() -> list[dict[str, int]]:
    if os.name != "nt":
        return []

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
    """Retrieve the first visible top-level window in Z-order that is NOT Blinky itself
    or a Windows system shell.

    On non-Windows platforms, this returns None since UI Automation is Windows-only.
    """
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
                
                # Fetch process info
                process_id = w.process_id()

                # If caller locked a specific PID, only match that process
                if target_pid is not None and process_id != target_pid:
                    continue

                process_name = psutil.Process(process_id).name().lower()
                
                # Exclude Blinky, Tauri, or prompt bars
                if "blinky" in process_name or "tauri" in process_name or "blinky" in title.lower():
                    continue

                if is_ignored_overlay_window(process_name, title):
                    LOGGER.info("Ignoring overlay window while selecting target: %s (%s)", title, process_name)
                    continue
                
                # Exclude Windows system shells and background services
                if process_name in {
                    "searchhost.exe",
                    "shellexperiencehost.exe",
                    "startmenuexperiencehost.exe",
                    "lockapp.exe",
                    "systemsettings.exe"
                }:
                    continue
                
                # Exclude Taskbar, desktop manager, and OS settings screens
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
        
    # Fallback to standard get_active() if custom resolution fails
    try:
        from pywinauto import Desktop
        active = Desktop(backend="uia").get_active()
        process_name = psutil.Process(active.process_id()).name().lower()
        title = active.window_text()
        if is_ignored_overlay_window(process_name, title):
            LOGGER.info("Ignoring active overlay fallback window: %s (%s)", title, process_name)
            return None
        return active
    except Exception:
        return None


def get_active_window(window=None, target_pid: int | None = None) -> dict:
    if os.name == "nt":
        try:
            w = get_target_window_element(window=window, target_pid=target_pid)
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
    else:
        # Linux Active Window resolution
        # 1. Try xdotool
        try:
            active_window_id = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
            pid = subprocess.check_output(["xdotool", "getwindowpid", active_window_id]).decode().strip()
            pid_num = int(pid)
            title = subprocess.check_output(["xdotool", "getwindowname", active_window_id]).decode("utf-8", errors="ignore").strip()
            process_name = psutil.Process(pid_num).name()
            return {
                "title": title,
                "process": process_name,
                "supported": is_process_supported(process_name),
            }
        except Exception:
            pass

        # 2. Try xprop
        try:
            active_win_out = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"]).decode().strip()
            win_id = active_win_out.split()[-1]
            if win_id.startswith("0x"):
                pid_out = subprocess.check_output(["xprop", "-id", win_id, "_NET_WM_PID", "_NET_WM_PID"]).decode().strip()
                pid_num = int(pid_out.split("=")[-1].strip())
                name_out = subprocess.check_output(["xprop", "-id", win_id, "WM_NAME"]).decode("utf-8", errors="ignore").strip()
                title = name_out.split("=")[-1].strip().strip('"')
                process_name = psutil.Process(pid_num).name()
                return {
                    "title": title,
                    "process": process_name,
                    "supported": is_process_supported(process_name),
                }
        except Exception:
            pass

        # Wayland / Unsupported desktop environment fallback
        session = os.environ.get("XDG_SESSION_TYPE", "wayland").lower()
        return {
            "title": "Linux Desktop",
            "process": session,
            "supported": False,
        }
