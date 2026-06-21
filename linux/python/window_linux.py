from __future__ import annotations

import os
import subprocess
import psutil
from utils.logging import get_logger

LOGGER = get_logger("blinky.window")


def get_active_window_linux() -> dict:
    try:
        active_window_id = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
        pid = subprocess.check_output(["xdotool", "getwindowpid", active_window_id]).decode().strip()
        pid_num = int(pid)
        title = subprocess.check_output(["xdotool", "getwindowname", active_window_id]).decode("utf-8", errors="ignore").strip()
        process_name = psutil.Process(pid_num).name()
        from utils.window import is_process_supported
        return {
            "title": title,
            "process": process_name,
            "supported": is_process_supported(process_name),
        }
    except Exception:
        pass

    try:
        active_win_out = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"]).decode().strip()
        win_id = active_win_out.split()[-1]
        if win_id.startswith("0x"):
            pid_out = subprocess.check_output(["xprop", "-id", win_id, "_NET_WM_PID"]).decode().strip()
            pid_num = int(pid_out.split("=")[-1].strip())
            name_out = subprocess.check_output(["xprop", "-id", win_id, "WM_NAME"]).decode("utf-8", errors="ignore").strip()
            title = name_out.split("=")[-1].strip().strip('"')
            process_name = psutil.Process(pid_num).name()
            from utils.window import is_process_supported
            return {
                "title": title,
                "process": process_name,
                "supported": is_process_supported(process_name),
            }
    except Exception:
        pass

    session = os.environ.get("XDG_SESSION_TYPE", "wayland").lower()
    return {
        "title": "Linux Desktop",
        "process": session,
        "supported": False,
    }
