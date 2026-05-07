from __future__ import annotations

import psutil

from utils.logging import get_logger

LOGGER = get_logger("clicky.window")

SUPPORTED_PROCESSES = {
    "code.exe",
    "chrome.exe",
    "mspaint.exe",
    "explorer.exe",
}


def get_active_window() -> dict:
    try:
        from pywinauto import Desktop

        window = Desktop(backend="uia").get_active()
        process_id = window.process_id()
        process_name = psutil.Process(process_id).name()
        title = window.window_text()
        return {
            "title": title,
            "process": process_name,
            "supported": process_name.lower() in SUPPORTED_PROCESSES,
        }
    except Exception as exc:
        LOGGER.warning("Could not inspect active window: %s", exc)
        return {"title": "Unknown window", "process": "unknown", "supported": False}
