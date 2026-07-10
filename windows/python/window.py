from __future__ import annotations

import os
import psutil
from utils.logging import get_logger

LOGGER = get_logger("blinky.window")

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

IGNORED_SYSTEM_PROCESSES = {
    "searchhost.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "lockapp.exe",
    "svchost.exe",
    "conhost.exe",
    "sihost.exe",
    "dwm.exe",
    "ctfmon.exe",
    "runtimebroker.exe",
    "trae.exe",
    "blinky.exe",
}

# explorer.exe hosts both real File-Explorer windows (which have a title like
# "C:\Users\...") and invisible shell chrome: Progman (desktop), Shell_TrayWnd
# (taskbar), WorkerW (desktop wallpaper), etc.  We want to skip the latter.
EXPLORER_SHELL_WINDOW_CLASSES = {
    "progman",
    "shell_traywnd",
    "workerw",
    "button",          # Start button in some Windows versions
    "toplevelhwnd",
    "taskbar",
}


def _is_ignored_overlay_window(process_name: str, title: str) -> bool:
    name_lower = process_name.lower().strip()
    title_lower = title.lower().strip()
    return name_lower in IGNORED_OVERLAY_PROCESSES or any(hint in title_lower for hint in IGNORED_OVERLAY_TITLE_HINTS)


def _is_window_cloaked(hwnd) -> bool:
    if not hwnd:
        return False
    try:
        import ctypes
        dwmapi = ctypes.windll.dwmapi
        cloaked = ctypes.c_int(0)
        # DWMWA_CLOAKED = 14
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, 
            14, 
            ctypes.byref(cloaked), 
            ctypes.sizeof(cloaked)
        )
        if hr == 0:
            return cloaked.value != 0
    except Exception:
        pass
    return False


def _is_system_session(pid: int) -> bool:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        session_id = ctypes.c_ulong()
        if kernel32.ProcessIdToSessionId(pid, ctypes.byref(session_id)):
            return session_id.value == 0
    except Exception:
        pass
    return False


def _get_target_window_element_impl(window=None, target_pid: int | None = None):
    if os.name != "nt":
        return None

    if window is not None:
        return window

    try:
        import ctypes
        from pywinauto import Desktop
        
        user32 = ctypes.windll.user32
        
        # Get Blinky processes (current python process and parent tauri process)
        blinky_pids = {os.getpid(), os.getppid()}
            
        next_hwnd = user32.GetForegroundWindow() if user32.GetForegroundWindow() else user32.GetTopWindow(None)
        
        fallback_hwnd = None
        fallback_title = ""
        fallback_process_name = ""
 
        # GW_HWNDNEXT = 2
        while next_hwnd:
            if user32.IsWindowVisible(next_hwnd) and not user32.IsIconic(next_hwnd) and not _is_window_cloaked(next_hwnd):
                # Get PID
                pid_val = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(next_hwnd, ctypes.byref(pid_val))
                pid = pid_val.value
                
                # Skip system session processes (Session 0 services/background tasks)
                if _is_system_session(pid):
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
 
                # Skip Blinky's own windows
                if pid in blinky_pids:
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
                    
                # Skip system processes
                if process_name in IGNORED_SYSTEM_PROCESSES:
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                    
                # Get window title FIRST before any checks that need it!
                length = user32.GetWindowTextLengthW(next_hwnd)
                title = ""
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(next_hwnd, buffer, length + 1)
                    title = buffer.value
                    
                # Skip ignored overlay processes
                if _is_ignored_overlay_window(process_name, title):
                    next_hwnd = user32.GetWindow(next_hwnd, 2)
                    continue
                
                # Skip explorer.exe shell chrome (desktop, taskbar, tray).
                # Real File-Explorer windows always have a non-empty title.
                # Shell chrome windows (Progman, Shell_TrayWnd, WorkerW) either
                # have no title or a known shell window class.
                if process_name == "explorer.exe":
                    # Check window class name
                    class_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(next_hwnd, class_buf, 256)
                    win_class = class_buf.value.lower()
                    if win_class in EXPLORER_SHELL_WINDOW_CLASSES or not title:
                        if not fallback_hwnd:
                            fallback_hwnd = next_hwnd
                            fallback_title = title
                            fallback_process_name = process_name
                        next_hwnd = user32.GetWindow(next_hwnd, 2)
                        continue

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
            
        if fallback_hwnd:
            try:
                target_w = Desktop(backend="uia").window(handle=fallback_hwnd)
                if target_w.exists():
                    LOGGER.info("Detected target application window via Z-order fallback hwnd: %s (%s)", fallback_title, fallback_process_name)
                    return target_w
            except Exception as pywinauto_exc:
                LOGGER.debug("Failed to wrap fallback hwnd %d in pywinauto: %s", fallback_hwnd, pywinauto_exc)

    except Exception as exc:
        LOGGER.warning("Failed to scan Windows window handles: %s", exc)

    # Fallback to Z-order Desktop scan
    try:
        from pywinauto import Desktop
        windows = Desktop(backend="uia").windows()
        fallback_w = None
        for w in windows:
            try:
                if not w.is_visible() or _is_window_cloaked(w.handle):
                    continue
                try:
                    if w.is_minimized():
                        continue
                except Exception:
                    pass
                title = w.window_text()
                
                process_id = w.process_id()
                if target_pid is not None and process_id != target_pid:
                    continue
                    
                if _is_system_session(process_id):
                    continue
                    
                process_name = psutil.Process(process_id).name().lower()
                if "blinky" in process_name or "tauri" in process_name or (title and "blinky" in title.lower()):
                    continue
                    
                if _is_ignored_overlay_window(process_name, title):
                    continue
                    
                if process_name in IGNORED_SYSTEM_PROCESSES:
                    continue
                
                # Skip explorer.exe shell chrome (desktop, taskbar, tray).
                # Real File-Explorer windows always have a non-empty title.
                if process_name == "explorer.exe" and not title:
                    if not fallback_w:
                        fallback_w = w
                    continue
                    
                LOGGER.info("Detected target application window: %s (%s)", title, process_name)
                return w
            except Exception:
                continue
        if fallback_w:
            LOGGER.info("Detected target application window (fallback): %s (%s)", fallback_w.window_text(), "explorer.exe")
            return fallback_w
    except Exception:
        pass
        
    return None


def get_target_window_element(window=None, target_pid: int | None = None):
    return _get_target_window_element_impl(window, target_pid)
