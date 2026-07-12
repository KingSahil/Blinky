from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use")

from computer_use.tools import (
    ToolResult, normalize_app_name, display_app_name, SAFE_PROCESS_ALIASES,
    APP_PROTOCOLS, KNOWN_EXECUTABLE_PATHS,
)


def open_app_tool_impl(app_name: str) -> ToolResult:
    app = normalize_app_name(app_name)
    if not app:
        return ToolResult(False, "open_app", "I need an app name to open.", {})

    if os.name != "nt":
        return ToolResult(False, "open_app", "Opening desktop apps is currently supported on Windows only.", {"app_name": app})

    protocol = APP_PROTOCOLS.get(app)
    if protocol:
        try:
            os.startfile(protocol)
            time.sleep(1.0)
            return ToolResult(True, "open_app", f"Opened {display_app_name(app_name, app)}.", {"app_name": app, "method": "app_protocol", "protocol": protocol})
        except Exception as exc:
            LOGGER.warning("Protocol launch failed for %s: %s", app, exc)

    for path in KNOWN_EXECUTABLE_PATHS.get(app, []):
        if not os.path.exists(path):
            continue
        try:
            subprocess.Popen([path])
            time.sleep(0.8)
            return ToolResult(True, "open_app", f"Opened {display_app_name(app_name, app)}.", {"app_name": app, "method": "known_path", "path": path})
        except Exception as exc:
            LOGGER.warning("Known path launch failed for %s via %s: %s", app, path, exc)

    from computer_use.tools import find_start_app
    start_app = find_start_app(app)
    if start_app:
        app_id = str(start_app.get("AppID", "")).strip()
        name = str(start_app.get("Name", app)).strip() or app
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
            time.sleep(1.0)
            return ToolResult(True, "open_app", f"Opened {name}.", {"app_name": name, "method": "start_apps_appid", "app_id": app_id})
        except Exception as exc:
            LOGGER.warning("StartApps launch failed for %s: %s", app, exc)

    alias = SAFE_PROCESS_ALIASES.get(app)
    if alias:
        try:
            subprocess.Popen([alias])
            time.sleep(0.8)
            return ToolResult(True, "open_app", f"Opened {app_name.strip()}.", {"app_name": app, "method": "process_alias", "alias": alias})
        except Exception as exc:
            LOGGER.warning("Process alias launch failed for %s: %s", app, exc)

    from computer_use.tools import open_app_via_windows_search
    search_result = open_app_via_windows_search(app)
    if search_result.success:
        return search_result

    return ToolResult(False, "open_app", f"I couldn't find {display_app_name(app_name, app)} installed.", {"app_name": app, "attempts": ["protocol", "known_path", "start_apps", "process_alias", "windows_search"]})


def open_app_via_windows_search_impl(app_name: str) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "open_app", "Windows Search fallback is only available on Windows.", {"app_name": app_name})

    try:
        from pywinauto.keyboard import send_keys

        send_keys("{VK_LWIN down}s{VK_LWIN up}")
        time.sleep(0.4)
        send_keys(app_name, with_spaces=True)
        time.sleep(0.8)
        from computer_use.tools import find_windows_search_result, click_item_center
        match = find_windows_search_result(app_name)
        if match:
            click_item_center(match)
            time.sleep(1.0)
            return ToolResult(
                True,
                "open_app",
                f"Found {display_app_name(app_name, app_name)} in Windows Search and opened it.",
                {"app_name": app_name, "method": "windows_search_screen_match", "matched_text": match.get("text", "")},
            )
        send_keys("{ENTER}")
        time.sleep(1.2)
        return ToolResult(True, "open_app", f"Searched Windows and opened {display_app_name(app_name, app_name)}.", {"app_name": app_name, "method": "windows_search_enter"})
    except Exception as exc:
        LOGGER.warning("Windows Search launch failed for %s: %s", app_name, exc)
        return ToolResult(False, "open_app", f"I could not open {display_app_name(app_name, app_name)} from Windows Search.", {"app_name": app_name, "method": "windows_search_enter", "error": str(exc)})


def find_windows_search_result_impl(app_name: str) -> dict[str, Any] | None:
    try:
        from utils.matching import find_best_match
        from uia import get_visible_ui_text

        items = get_visible_ui_text(include_unlabeled=False)
        return find_best_match(app_name, items, f"Open {app_name} from the Windows Search results.")
    except Exception as exc:
        LOGGER.warning("Could not inspect Windows Search results for %s: %s", app_name, exc)
        return None


def find_start_app_impl(app_name: str) -> dict[str, Any] | None:
    safe_query = normalize_app_name(app_name)
    if not safe_query:
        return None

    command = "& { param($query); $apps = Get-StartApps | Where-Object { $_.Name -like \"*$query*\" } | Select-Object -First 1 Name,AppID; if ($apps) { $apps | ConvertTo-Json -Compress } }"
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command, f'"{safe_query}"'],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        LOGGER.warning("Get-StartApps lookup failed: %s", exc)
        return None

    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        parsed = json.loads(completed.stdout)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) and parsed.get("AppID") else None


def shortcut_tool_impl(shortcut: str) -> ToolResult:
    from computer_use.tools import normalize_shortcut

    normalized = normalize_shortcut(shortcut)
    if not normalized:
        return ToolResult(False, "shortcut", "I could not understand that shortcut.", {"shortcut": shortcut})
    if os.name != "nt":
        return ToolResult(False, "shortcut", "Keyboard shortcuts are currently supported on Windows only.", {"shortcut": shortcut})

    try:
        from pywinauto.keyboard import CODES, send_keys

        # Register standard virtual media keys dynamically in pywinauto
        if "VK_MEDIA_PLAY_PAUSE" not in CODES:
            CODES["VK_MEDIA_PLAY_PAUSE"] = 0xB3
        if "VK_MEDIA_STOP" not in CODES:
            CODES["VK_MEDIA_STOP"] = 0xB2
        if "VK_MEDIA_NEXT_TRACK" not in CODES:
            CODES["VK_MEDIA_NEXT_TRACK"] = 0xB0
        if "VK_MEDIA_PREV_TRACK" not in CODES:
            CODES["VK_MEDIA_PREV_TRACK"] = 0xB1

        send_keys(normalized)
        time.sleep(0.5)
        return ToolResult(True, "shortcut", f"Pressed {shortcut}.", {"shortcut": shortcut, "pywinauto_keys": normalized})
    except Exception as exc:
        return ToolResult(False, "shortcut", f"I couldn't press {shortcut}: {exc}", {"shortcut": shortcut})
