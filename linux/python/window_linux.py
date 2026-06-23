from __future__ import annotations

import os
import subprocess
import json
import psutil
from utils.logging import get_logger

LOGGER = get_logger("blinky.window")


def _kwin_active_window() -> dict | None:
    """Get the active/focused window via computer-use-linux MCP (KWin backend)."""
    try:
        from computer_use.linux_mcp import get_client
        client = get_client()
        result = client.call_tool("focused_window", {})
        if not isinstance(result, dict):
            return None
        window = result.get("window", result)
        title = str(window.get("title", ""))
        app_id = str(window.get("app_id", ""))
        bounds = window.get("bounds", {})
        if not title and not app_id:
            return None
        from utils.window import is_process_supported
        return {
            "title": title,
            "process": app_id.rsplit(".", 1)[-1] if "." in app_id else app_id,
            "supported": is_process_supported(app_id),
            "x": bounds.get("x", 0),
            "y": bounds.get("y", 0),
            "width": bounds.get("width", 0),
            "height": bounds.get("height", 0),
        }
    except Exception as e:
        LOGGER.debug("KWin focused window query failed: %s", e)
        return None


def get_active_window_linux() -> dict:
    # 1. Try KWin on Wayland first
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland":
        result = _kwin_active_window()
        if result:
            LOGGER.info("Active window via KWin: %s", result.get("title", ""))
            return result

    # 2. Try xdotool (X11/XWayland)
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

    # 3. Try xprop (X11)
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

    return {
        "title": "Linux Desktop",
        "process": session,
        "supported": False,
    }
