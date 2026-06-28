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
    "whatsapp",
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

STOP_SPOTIFY_RE = re.compile(
    r"^\s*(?:stop|pause|resume)(?:\s+(?:the\s+)?(?:music|song|spotify|video|playback))?\s*$",
    re.IGNORECASE,
)

SEEK_FORWARD_RE = re.compile(
    r"^\s*(?:(?:fast\s*forward|forward|seek\s+forward|skip\s+forward|go\s+forward|seek)\s*(?:the\s+)?(?:music|song|spotify|video|playback\s+)?(?:forward\s+)?(?:by\s+)?(?P<value>\d+)?\s*(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*(?:forward)?|skip\s+(?:the\s+)?(?:music|song|spotify|video|playback\s+)?(?:by\s+)?(?P<value_skip>\d+)\s*(?P<unit_skip>s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*(?:forward)?)\s*(?:in\s+|on\s+|of\s+)?(?:the\s+)?(?:music|song|spotify|video|playback)?\s*$",
    re.IGNORECASE,
)

SEEK_BACKWARD_RE = re.compile(
    r"^\s*(?:(?:rewind|backward|back|seek\s+back(?:ward)?|skip\s+back(?:ward)?|go\s+back(?:ward)?)\s*(?:the\s+)?(?:music|song|spotify|video|playback\s+)?(?:back(?:ward)?\s+)?(?:by\s+)?(?P<value>\d+)?\s*(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*(?:back|backward)?|skip\s+(?:the\s+)?(?:music|song|spotify|video|playback\s+)?(?:by\s+)?(?P<value_skip>\d+)\s*(?P<unit_skip>s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*(?:back|backward))\s*(?:in\s+|on\s+|of\s+)?(?:the\s+)?(?:music|song|spotify|video|playback)?\s*$",
    re.IGNORECASE,
)



NEXT_TRACK_RE = re.compile(
    r"^\s*(?:next\s+(?:song|track|music|video)|skip\s+(?:the\s+)?(?:song|track|music|video|playback)|play\s+next|next)\s*$",
    re.IGNORECASE,
)

PREV_TRACK_RE = re.compile(
    r"^\s*(?:prev(?:ious)?\s+(?:song|track|music|video)|play\s+prev(?:ious)?|prev(?:ious)?)\s*$",
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


def handle_media_playback_action(extracted_params: dict, query: str) -> ToolResult:
    media_action = str(extracted_params.get("media_action", "play")).lower().strip()
    if media_action in ("pause", "stop", "resume"):
        return shortcut_tool("media_play_pause")
    elif media_action == "next":
        return shortcut_tool("media_next")
    elif media_action == "prev":
        return shortcut_tool("media_prev")
    elif media_action == "seek":
        seek_sec = extracted_params.get("seek_seconds")
        try:
            seconds = int(seek_sec) if seek_sec is not None else 10
        except Exception:
            seconds = 10
        forward = seconds >= 0
        from .tools import seek_spotify_tool
        return seek_spotify_tool(abs(seconds), forward=forward)
    else:
        # Default to play song
        song = extracted_params.get("song_name")
        pform = str(extracted_params.get("platform", "spotify")).lower().strip()
        query_lower = query.lower()
        if pform == "youtube" or "youtube" in query_lower or "you tube" in query_lower:
            from .tools import play_youtube_video_tool
            return play_youtube_video_tool(song) if song else play_youtube_video_tool(query)
        else:
            from .tools import play_spotify_track_tool
            return play_spotify_track_tool(song) if song else play_spotify_track_tool(query)


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

    if STOP_SPOTIFY_RE.match(question_cleaned):
        return shortcut_tool("media_play_pause")

    # Spotify seeking and track skipping control
    seek_forward_match = SEEK_FORWARD_RE.match(question_cleaned)
    if seek_forward_match:
        val_str = seek_forward_match.group("value") or seek_forward_match.group("value_skip")
        unit_str = seek_forward_match.group("unit") or seek_forward_match.group("unit_skip")
        if val_str:
            val = int(val_str)
            seconds = val * 60 if unit_str and unit_str.lower().startswith("m") else val
        else:
            seconds = 10
        from .tools import seek_spotify_tool
        return seek_spotify_tool(seconds, forward=True)

    seek_backward_match = SEEK_BACKWARD_RE.match(question_cleaned)
    if seek_backward_match:
        val_str = seek_backward_match.group("value") or seek_backward_match.group("value_skip")
        unit_str = seek_backward_match.group("unit") or seek_backward_match.group("unit_skip")
        if val_str:
            val = int(val_str)
            seconds = val * 60 if unit_str and unit_str.lower().startswith("m") else val
        else:
            seconds = 10
        from .tools import seek_spotify_tool
        return seek_spotify_tool(seconds, forward=False)



    if NEXT_TRACK_RE.match(question_cleaned):
        return shortcut_tool("media_next")

    if PREV_TRACK_RE.match(question_cleaned):
        return shortcut_tool("media_prev")


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
