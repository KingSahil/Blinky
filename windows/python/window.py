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
        import ctypes
        from pywinauto import Desktop
        
        user32 = ctypes.windll.user32
        
        # Get Blinky window (which is currently active)
        active_hwnd = user32.GetForegroundWindow()
        blinky_pid = None
        if active_hwnd:
            pid_val = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(active_hwnd, ctypes.byref(pid_val))
            blinky_pid = pid_val.value
            
        next_hwnd = active_hwnd if active_hwnd else user32.GetTopWindow(None)
        
        # GW_HWNDNEXT = 2
        while next_hwnd:
            if user32.IsWindowVisible(next_hwnd):
                # Get PID
                pid_val = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(next_hwnd, ctypes.byref(pid_val))
                pid = pid_val.value
                
                # Skip Blinky's own windows
                if blinky_pid and pid == blinky_pid:
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                    
                try:
                    process_name = psutil.Process(pid).name().lower()
                except Exception:
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                    
                if "blinky" in process_name or "tauri" in process_name:
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                    
                # Skip system overlays
                if process_name in {
                    "searchhost.exe",
                    "shellexperiencehost.exe",
                    "startmenuexperiencehost.exe",
                    "lockapp.exe",
                }:
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                    
                # Get window title
                length = user32.GetWindowTextLengthW(next_hwnd)
                title = ""
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(next_hwnd, buffer, length + 1)
                    title = buffer.value
                
                # If target_pid is specified, match it
                if target_pid is not None and pid != target_pid:
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                
                # We found our target window!
                # Resolve it using pywinauto from its handle
                try:
                    target_w = Desktop(backend="uia").window(handle=next_hwnd)
                    if target_w.exists():
                        LOGGER.info("Detected target application window via Z-order hwnd: %s (%s)", title, process_name)
                        return target_w
                except Exception as pywinauto_exc:
                    LOGGER.debug("Failed to wrap hwnd %d in pywinauto: %s", next_hwnd, pywinauto_exc)
                    
            next_hwnd = user32.GetWindow(next_hwnd, 2)
            
    except Exception as exc:
        LOGGER.warning("Failed to scan Windows window handles: %s", exc)

    # Fallback to Z-order Desktop scan
    try:
        from pywinauto import Desktop
        windows = Desktop(backend="uia").windows()
        for w in windows:
            try:
                if not w.is_visible():
                    continue
                title = w.window_text()
                
                process_id = w.process_id()
                if target_pid is not None and process_id != target_pid:
                    continue
                    
                process_name = psutil.Process(process_id).name().lower()
                if "blinky" in process_name or "tauri" in process_name or (title and "blinky" in title.lower()):
                    continue
                    
                if process_name in {
                    "searchhost.exe",
                    "shellexperiencehost.exe",
                    "startmenuexperiencehost.exe",
                    "lockapp.exe",
                }:
                    continue
                    
                LOGGER.info("Detected target application window: %s (%s)", title, process_name)
                return w
            except Exception:
                continue
    except Exception:
        pass
        
    return None


def get_target_window_element(window=None, target_pid: int | None = None):
    return _get_target_window_element_impl(window, target_pid)
