from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use")


@dataclass
class ToolResult:
    success: bool
    tool: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool": self.tool,
            "message": self.message,
            "details": self.details,
        }


SAFE_PROCESS_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
}

APP_PROTOCOLS = {
    "edge": "microsoft-edge:",
    "microsoft edge": "microsoft-edge:",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "whats app": "whatsapp:",
}

KNOWN_EXECUTABLE_PATHS = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "microsoft edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
}

APP_NAME_ALIASES = {
    "ms edge": "edge",
    "microsoft edge browser": "microsoft edge",
    "whats app": "whatsapp",
    "whatsapp desktop": "whatsapp",
    "spotify desktop": "spotify",
}


def open_app_tool(app_name: str) -> ToolResult:
    app = normalize_app_name(app_name)
    if not app:
        return ToolResult(False, "open_app", "I need an app name to open.", {})

    if os.name != "nt":
        return ToolResult(False, "open_app", "Opening desktop apps is currently supported on Windows only.", {"app_name": app})

    protocol = APP_PROTOCOLS.get(app)
    if protocol:
        try:
            os.startfile(protocol)  # type: ignore[attr-defined]
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

    search_result = open_app_via_windows_search(app)
    if search_result.success:
        return search_result

    return ToolResult(False, "open_app", f"I couldn't find {display_app_name(app_name, app)} installed.", {"app_name": app, "attempts": ["protocol", "known_path", "start_apps", "process_alias", "windows_search"]})


def open_app_via_windows_search(app_name: str) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "open_app", "Windows Search fallback is only available on Windows.", {"app_name": app_name})

    try:
        from pywinauto.keyboard import send_keys

        send_keys("{VK_LWIN down}s{VK_LWIN up}")
        time.sleep(0.4)
        send_keys(app_name, with_spaces=True)
        time.sleep(0.8)
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


def find_windows_search_result(app_name: str) -> dict[str, Any] | None:
    try:
        from utils.matching import find_best_match
        from utils.uia import get_visible_ui_text

        items = get_visible_ui_text(include_unlabeled=False)
        return find_best_match(app_name, items, f"Open {app_name} from the Windows Search results.")
    except Exception as exc:
        LOGGER.warning("Could not inspect Windows Search results for %s: %s", app_name, exc)
        return None


def click_item_center(item: dict[str, Any]) -> None:
    from pywinauto.mouse import click

    x = int(float(item.get("x") or 0) + float(item.get("width") or 0) / 2)
    y = int(float(item.get("y") or 0) + float(item.get("height") or 0) / 2)
    click(button="left", coords=(x, y))


def shortcut_tool(shortcut: str) -> ToolResult:
    normalized = normalize_shortcut(shortcut)
    if not normalized:
        return ToolResult(False, "shortcut", "I could not understand that shortcut.", {"shortcut": shortcut})
    if os.name != "nt":
        return ToolResult(False, "shortcut", "Keyboard shortcuts are currently supported on Windows only.", {"shortcut": shortcut})

    try:
        from pywinauto.keyboard import send_keys

        send_keys(normalized)
        time.sleep(0.5)
        return ToolResult(True, "shortcut", f"Pressed {shortcut}.", {"shortcut": shortcut, "pywinauto_keys": normalized})
    except Exception as exc:
        return ToolResult(False, "shortcut", f"I couldn't press {shortcut}: {exc}", {"shortcut": shortcut})


def find_start_app(app_name: str) -> dict[str, Any] | None:
    safe_query = normalize_app_name(app_name)
    if not safe_query:
        return None

    command = "\n".join(
        [
            "$query = $args[0]",
            "$apps = Get-StartApps | Where-Object { $_.Name -like \"*$query*\" } | Select-Object -First 1 Name,AppID",
            "if ($apps) { $apps | ConvertTo-Json -Compress }",
        ]
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command, safe_query],
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


def normalize_app_name(value: str) -> str:
    text = " ".join(str(value).strip().lower().split())
    text = re.sub(
        r"\b(installed|desktop|app|application|please|on my pc|on pc|in my pc|from my pc|for me)\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9 .+_-]", "", text)
    text = " ".join(text.split()).strip(" ._-")
    return APP_NAME_ALIASES.get(text, text)


def display_app_name(original: str, normalized: str) -> str:
    display = " ".join(str(original).strip().split())
    cleaned = normalize_app_name(display)
    if cleaned == normalized and display:
        display = re.sub(r"\b(installed|desktop|app|application|please|on my pc|on pc|in my pc|from my pc|for me)\b", "", display, flags=re.IGNORECASE)
        display = " ".join(display.split()).strip()
    return display or normalized.title()


def normalize_shortcut(shortcut: str) -> str:
    parts = [part.strip().lower() for part in re.split(r"[+ ]+", shortcut) if part.strip()]
    if not parts:
        return ""

    key = parts[-1]
    modifiers = parts[:-1]
    output = ""
    for modifier in modifiers:
        if modifier in {"ctrl", "control"}:
            output += "^"
        elif modifier == "alt":
            output += "%"
        elif modifier == "shift":
            output += "+"
        elif modifier in {"win", "windows", "super"}:
            output += "{VK_LWIN down}"
        else:
            return ""

    if len(key) == 1:
        output += key
    else:
        special = {
            "enter": "{ENTER}",
            "return": "{ENTER}",
            "tab": "{TAB}",
            "escape": "{ESC}",
            "esc": "{ESC}",
            "space": "{SPACE}",
        }.get(key)
        if not special:
            return ""
        output += special

    if any(modifier in {"win", "windows", "super"} for modifier in modifiers):
        output += "{VK_LWIN up}"
    return output
