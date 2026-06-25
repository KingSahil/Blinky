from __future__ import annotations

import platform
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

IS_LINUX = platform.system() == "Linux"

OPEN_APP_RE = re.compile(
    r"^\s*(?:open|launch|start)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})\s*(?:app|application)?\s*$",
    re.IGNORECASE,
)

PLAY_SPOTIFY_RE = re.compile(
    r"^\s*play\s+(?:spotify\s+(?P<song1>.+)|(?P<song2>.+?)\s+(?:in|on)\s+spotify)\s*$",
    re.IGNORECASE,
)

PLAY_YOUTUBE_RE = re.compile(
    r"^\s*play\s+(?:youtube\s+(?P<query1>.+)|(?P<query2>.+?)\s+(?:in|on)\s+youtube)\s*$",
    re.IGNORECASE,
)

LIST_WINDOWS_RE = re.compile(
    r"^\s*(?:list|show|enumerate|what)\s+(?:windows|apps|applications|desktop apps|open windows)\s*$",
    re.IGNORECASE,
)

GET_APP_STATE_RE = re.compile(
    r"^\s*(?:inspect|examine|analyze|show me|what'?s (?:in|on))\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})\s*(?:app|application|window)?\s*$",
    re.IGNORECASE,
)

CLICK_ELEMENT_RE = re.compile(
    r"^\s*(?:click|press|select|hit|push)\s+(?:the\s+)?(?P<element>.+?)(?:\s+(?:in|on)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})(?:\s*(?:app|application|window))?)?\s*$",
    re.IGNORECASE,
)

TYPE_TEXT_RE = re.compile(
    r"^\s*(?:type|enter|write|input)\s+(?P<text>.+?)(?:\s+(?:in|into|to)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60}))?\s*$",
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
    if len(words) > 3:
        known_long_apps = {"visual studio code", "windows media player", "mail and calendar"}
        if name_lower not in known_long_apps:
            return False
    if len(words) > 1:
        invalid_words = {"and", "or", "to", "in", "on", "at", "for", "with", "about", "from", "by", "search", "find", "how"}
        if any(w in invalid_words for w in words):
            if name_lower != "mail and calendar":
                return False
    return True


def try_run_agent_action(question: str, observation: dict[str, Any] | None = None) -> ToolResult | None:
    question_cleaned = question.strip().rstrip("?.!,;:")

    if wants_help_menu(question_cleaned, observation):
        return shortcut_tool("alt+h")

    play_match = PLAY_SPOTIFY_RE.match(question_cleaned)
    if play_match:
        song = play_match.group("song1") or play_match.group("song2")
        if song:
            from .tools import play_spotify_track_tool
            return play_spotify_track_tool(song.strip())

    play_yt_match = PLAY_YOUTUBE_RE.match(question_cleaned)
    if play_yt_match:
        query = play_yt_match.group("query1") or play_yt_match.group("query2")
        if query:
            from .tools import play_youtube_video_tool
            return play_youtube_video_tool(query.strip())

    # Linux desktop actions
    if IS_LINUX:
        result = _try_linux_action(question_cleaned)
        if result is not None:
            return result

    match = OPEN_APP_RE.match(question_cleaned)
    if match:
        app = cleanup_app_name(match.group("app"))
        if app and app not in {"help", "settings", "menu"}:
            if is_web_destination(app):
                if observation is not None:
                    return open_web_destination_tool(app)
                return None
            if not is_in_app_action(app) and looks_like_app_name(app):
                return open_app_tool(app)

    return None

def _try_linux_action(question: str) -> ToolResult | None:
    # List windows
    if LIST_WINDOWS_RE.match(question):
        from .tools import list_windows_tool
        return list_windows_tool()

    # Inspect an app
    app_match = GET_APP_STATE_RE.match(question)
    if app_match:
        app = app_match.group("app")
        if app and looks_like_app_name(app):
            from .tools import get_app_state_tool
            return get_app_state_tool(app)

    # Click an element
    click_match = CLICK_ELEMENT_RE.match(question)
    if click_match:
        element = click_match.group("element")
        app = click_match.group("app")
        if element:
            from .tools import click_element_tool
            return click_element_tool(name=element.strip())

    # Type text
    type_match = TYPE_TEXT_RE.match(question)
    if type_match:
        text = type_match.group("text")
        app = type_match.group("app")
        if text:
            from .tools import type_text_tool
            return type_text_tool(text.strip(), target_app=app.strip() if app else None)

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
