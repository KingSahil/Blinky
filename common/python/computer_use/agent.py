from __future__ import annotations

import re
from typing import Any

from .tools import ToolResult, open_app_tool, open_web_destination_tool, shortcut_tool


WEB_DESTINATION_NAMES = {
    "youtube",
    "you tube",
    "youtube music",
    "you tube music",
    "gmail",
    "google",
    "google search",
    "google drive",
    "google docs",
    "google sheets",
    "google slides",
    "whatsapp web",
    "facebook",
    "instagram",
    "x",
    "twitter",
    "linkedin",
    "reddit",
    "github",
    "chatgpt",
    "chat gpt",
}


OPEN_APP_RE = re.compile(
    r"^\s*(?:open|launch|start)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})\s*(?:app|application)?\s*$",
    re.IGNORECASE,
)

PLAY_SPOTIFY_RE = re.compile(
    r"^\s*play\s+(?:spotify\s+(?P<song1>.+)|(?P<song2>.+?)\s+(?:in|on)\s+spotify)\s*$",
    re.IGNORECASE,
)


def is_in_app_action(app_name: str) -> bool:
    app_lower = app_name.lower().strip()
    in_app_keywords = {
        "tab", "tabs", "settings", "menu", "sidebar", "extensions", "status", "profile",
        "chat", "chats", "bookmark", "bookmarks", "download", "downloads", "folder", "folders",
        "file", "files", "history", "recent", "preferences", "terminal", "console"
    }
    return any(re.search(rf"\b{re.escape(word)}\b", app_lower) for word in in_app_keywords)


def is_web_destination(app_name: str) -> bool:
    name_lower = " ".join(app_name.lower().strip().split())
    if not name_lower:
        return False
    if re.search(r"\b(?:https?://|www\.|[a-z0-9-]+\.[a-z]{2,})(?:\b|/)", name_lower):
        return True
    return name_lower in WEB_DESTINATION_NAMES


def looks_like_app_name(app_name: str) -> bool:
    name_lower = app_name.lower().strip()
    words = name_lower.split()
    if not words:
        return False
    # If it's too long, it's likely a description or query
    if len(words) > 3:
        # Allow known long apps
        known_long_apps = {"visual studio code", "windows media player", "mail and calendar"}
        if name_lower not in known_long_apps:
            return False
    # Check for prepositions or action-oriented words if it has multiple words
    if len(words) > 1:
        invalid_words = {"and", "or", "to", "in", "on", "at", "for", "with", "about", "from", "by", "search", "find", "how"}
        if any(w in invalid_words for w in words):
            # Exception for "mail and calendar"
            if name_lower != "mail and calendar":
                return False
    return True


def try_run_agent_action(question: str, observation: dict[str, Any] | None = None) -> ToolResult | None:
    # Clean trailing punctuation for robust matching of voice input/dictation
    question_cleaned = question.strip().rstrip("?.!,;:")

    if wants_help_menu(question_cleaned, observation):
        return shortcut_tool("alt+h")

    # Match play spotify request
    play_match = PLAY_SPOTIFY_RE.match(question_cleaned)
    if play_match:
        song = play_match.group("song1") or play_match.group("song2")
        if song:
            from .tools import play_spotify_track_tool
            return play_spotify_track_tool(song.strip())

    match = OPEN_APP_RE.match(question_cleaned)
    if match:
        app = cleanup_app_name(match.group("app"))
        if app and app not in {"help", "settings", "menu"}:
            if is_web_destination(app):
                return open_web_destination_tool(app)
            if not is_in_app_action(app) and looks_like_app_name(app):
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
