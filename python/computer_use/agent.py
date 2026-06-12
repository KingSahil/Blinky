from __future__ import annotations

import re
from typing import Any

from .tools import ToolResult, open_app_tool, shortcut_tool


OPEN_APP_RE = re.compile(
    r"^\s*(?:open|launch|start)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})\s*(?:app|application)?\s*$",
    re.IGNORECASE,
)


def try_run_agent_action(question: str, observation: dict[str, Any] | None = None) -> ToolResult | None:
    if wants_help_menu(question, observation):
        return shortcut_tool("alt+h")

    match = OPEN_APP_RE.match(question)
    if match:
        app = cleanup_app_name(match.group("app"))
        if app and app not in {"help", "settings", "menu"}:
            return open_app_tool(app)

    return None


def cleanup_app_name(value: str) -> str:
    text = " ".join(value.strip().split())
    text = re.sub(r"\b(app|application)$", "", text, flags=re.IGNORECASE).strip()
    return text


def wants_help_menu(question: str, observation: dict[str, Any] | None) -> bool:
    normalized = question.lower()
    if not any(phrase in normalized for phrase in {"open help", "help menu", "open the help"}):
        return False
    active_app = observation.get("active_app", {}) if isinstance(observation, dict) else {}
    process = str(active_app.get("process", "")).lower()
    app_context = str(observation.get("app_context", "")).lower() if isinstance(observation, dict) else ""
    return process in {"code.exe", "code"} or "shortcut: alt+h" in app_context
