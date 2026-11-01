import logging
import platform
import re
import time
from typing import Any

from . import tools
from .tools import (
    ToolResult,
    open_app_tool,
    open_web_destination_tool,
    open_web_search_tool,
    shortcut_tool,
    normalize_app_name,
    APP_PROTOCOLS,
    APP_NAME_ALIASES,
    SAFE_PROCESS_ALIASES,
    type_text_tool,
    play_spotify_track_tool,
    play_youtube_video_tool,
    seek_spotify_tool,
    list_windows_tool,
    get_app_state_tool,
)

def _get_tool(name: str):
    """Resolve tool implementation dynamically, supporting mocks on either computer_use.tools or computer_use.agent."""
    tools_val = getattr(tools, name, None)
    agent_val = globals().get(name)
    if hasattr(agent_val, "assert_called") or hasattr(agent_val, "mock_calls"):
        return agent_val
    return tools_val or agent_val

LOGGER = logging.getLogger("blinky.computer_use.agent")


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

SEARCH_WEB_RE = re.compile(
    r"^\s*(?:open\s+google\s+(?:and\s+)?(?:search|type|find)\s+(?:for\s+)?(?P<q1>.+)|(?:search|searching|find|look\s+up)\s+(?:for\s+)?(?P<q2>.+?)\s+(?:in|on)\s+google|search\s+google\s+for\s+(?P<q3>.+)|google\s+(?:search\s+)?(?P<q4>.+)|(?:search|searching|find|look\s+up)\s+(?:for\s+)?(?P<q5>(?:best\s+)?(?:restaurants?|cafes?|food|coffee|places|hotels?|gas\s+stations?|stores?|shops?|weather)\s+near\s+me(?:\s+online)?))\s*$",
    re.IGNORECASE,
)

OPEN_APP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60}?)(?:\s+(?:app|application|only|just|window|please))*\s*$",
    re.IGNORECASE,
)

OPEN_AND_TYPE_RE = re.compile(
    r"^\s*(?:open|launch|start)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60}?)(?:\s+(?:app|application))?\s*(?:and|then|,)\s*(?:type|write|enter|input)\s+(?:the\s+(?:text|words?)\s+)?(?P<text>.+?)(?:\s+(?:in|into|on)\s+it)?\s*$",
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
    r"^\s*(?:click|press|select|hit|push|tap)\s+(?:on\s+)?(?:the\s+)?(?P<element>.+?)(?:\s+(?:in|on)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})(?:\s*(?:app|application|window))?)?\s*$",
    re.IGNORECASE,
)

TYPE_TEXT_IN_APP_RE = re.compile(
    r"^\s*(?:type|enter|write|input)\s+(?P<text>.+?)\s+(?:in|into)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,60})\s*$",
    re.IGNORECASE,
)
TYPE_TEXT_TO_APP_RE = re.compile(
    r"^\s*(?:type|enter|write|input)\s+(?P<text>.+?)\s+to\s+(?:the\s+)?(?P<app>[a-zA-Z][a-zA-Z0-9 .+_-]{1,60})\s*$",
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
    if re.match(r"^cell\s+[a-zA-Z]{1,3}\d+$", name_lower):
        return False
    words = name_lower.split()
    if not words:
        return False
    if name_lower in {"screen", "my screen", "the screen", "this screen", "current screen", "desktop", "display"} or any(w in {"screen", "display"} for w in words):
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
        return _get_tool("shortcut_tool")("media_play_pause")
    elif media_action == "next":
        return _get_tool("shortcut_tool")("media_next")
    elif media_action == "prev":
        return _get_tool("shortcut_tool")("media_prev")
    elif media_action == "seek":
        seek_sec = extracted_params.get("seek_seconds")
        try:
            seconds = int(seek_sec) if seek_sec is not None else 10
        except Exception:
            seconds = 10
        forward = seconds >= 0
        return _get_tool("seek_spotify_tool")(abs(seconds), forward=forward)
    else:
        # Default to play song
        song = extracted_params.get("song_name")
        pform = str(extracted_params.get("platform", "spotify")).lower().strip()
        query_lower = query.lower()
        if pform == "youtube" or "youtube" in query_lower or "you tube" in query_lower:
            return _get_tool("play_youtube_video_tool")(song) if song else _get_tool("play_youtube_video_tool")(query)
        else:
            return _get_tool("play_spotify_track_tool")(song) if song else _get_tool("play_spotify_track_tool")(query)


def try_run_agent_action(question: str, observation: dict[str, Any] | None = None) -> ToolResult | None:
    question_cleaned = question.strip().rstrip("?.!,;:")

    # Fast Folder and File Explorer launcher (<15ms OS-level execution)
    try:
        from .folder_launcher import is_folder_or_explorer_request, open_folder_or_path
        if is_folder_or_explorer_request(question_cleaned):
            folder_res = open_folder_or_path(question_cleaned)
            if folder_res.get("success"):
                return ToolResult(
                    True,
                    "open_folder",
                    folder_res.get("message", "Opened folder in File Explorer."),
                    folder_res,
                )
    except Exception as exc:
        LOGGER.debug("Folder launcher action failed: %s", exc)

    # ESP32 physical light control
    try:
        from tools.esp32_light_tool import resolve_light_request, handle_request
        light_params = resolve_light_request(question_cleaned)
        if light_params:
            res = handle_request(light_params)
            msg = res.get("message") or ("Light turned off." if light_params.get("action") in ("turn_off", "off") else "Light color updated.")
            return ToolResult(
                res.get("success", False),
                "esp32_light",
                msg,
                res,
            )
    except Exception as exc:
        LOGGER.debug("ESP32 light action failed: %s", exc)

    if wants_help_menu(question_cleaned, observation):
        return _get_tool("shortcut_tool")("alt+h")

    play_match = PLAY_SPOTIFY_RE.match(question_cleaned)
    if play_match:
        song = play_match.group("song1") or play_match.group("song2")
        if song:
            return _get_tool("play_spotify_track_tool")(song.strip())

    play_yt_match = PLAY_YOUTUBE_RE.match(question_cleaned)
    if play_yt_match:
        query = play_yt_match.group("query1") or play_yt_match.group("query2")
        if query:
            return _get_tool("play_youtube_video_tool")(query.strip())

    if STOP_SPOTIFY_RE.match(question_cleaned):
        return _get_tool("shortcut_tool")("media_play_pause")

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
        return _get_tool("seek_spotify_tool")(seconds, forward=True)

    seek_backward_match = SEEK_BACKWARD_RE.match(question_cleaned)
    if seek_backward_match:
        val_str = seek_backward_match.group("value") or seek_backward_match.group("value_skip")
        unit_str = seek_backward_match.group("unit") or seek_backward_match.group("unit_skip")
        if val_str:
            val = int(val_str)
            seconds = val * 60 if unit_str and unit_str.lower().startswith("m") else val
        else:
            seconds = 10
        return _get_tool("seek_spotify_tool")(seconds, forward=False)

    if NEXT_TRACK_RE.match(question_cleaned):
        return _get_tool("shortcut_tool")("media_next")

    if PREV_TRACK_RE.match(question_cleaned):
        return _get_tool("shortcut_tool")("media_prev")

    # Spreadsheet creation fast-path
    try:
        from tools.spreadsheet_tool import resolve_spreadsheet_request, handle_request as handle_spreadsheet_request
        sheet_params = resolve_spreadsheet_request(question_cleaned)
        if sheet_params:
            sheet_res = handle_spreadsheet_request(sheet_params)
            msg = sheet_res.get("message") or "Created Microsoft Excel spreadsheet successfully."
            return ToolResult(
                sheet_res.get("success", True),
                "spreadsheet_tool",
                msg,
                sheet_res,
            )
    except Exception as exc:
        LOGGER.debug("Spreadsheet tool action failed: %s", exc)

    # Windows-Use fast-path (e.g. Notepad new tab, type, or compound desktop tasks)
    try:
        from .windows_use_engine import resolve_windows_use_request, handle_windows_use_request
        wu_params = resolve_windows_use_request(question_cleaned)
        if wu_params:
            wu_res = handle_windows_use_request(wu_params)
            msg = wu_res.get("message") or "Windows UI action completed."
            return ToolResult(
                wu_res.get("success", False),
                "windows_use_tool",
                msg,
                wu_res,
            )
    except Exception as exc:
        LOGGER.debug("Windows-Use direct agent action failed: %s", exc)

    # Desktop actions (click element, type text, list windows, get app state)
    result = _try_desktop_action(question_cleaned)
    if result is not None:
        return result

    search_match = SEARCH_WEB_RE.match(question_cleaned)
    if search_match:
        query = (
            search_match.group("q1")
            or search_match.group("q2")
            or search_match.group("q3")
            or search_match.group("q4")
            or search_match.group("q5")
        )
        if query:
            return _get_tool("open_web_search_tool")(query.strip())

    open_and_type_match = OPEN_AND_TYPE_RE.match(question_cleaned)
    if open_and_type_match:
        from .vercel_engine import desktop_enabled
        if desktop_enabled():
            # Let the selected ref-based engine own compound UI editing;
            # do not launch/type using the old foreground-keyboard recipe.
            return None
    if open_and_type_match:
        app = cleanup_app_name(open_and_type_match.group("app"))
        raw_text = open_and_type_match.group("text").strip().strip("'\"")
        if app and raw_text:
            open_res = _get_tool("open_app_tool")(app)
            # Event-driven wait: poll up to 0.8s for target app to focus instead of hard sleeping
            deadline = time.monotonic() + 0.8
            while time.monotonic() < deadline:
                try:
                    active = _get_tool("get_app_state_tool")()
                    if active and app.lower() in str(active.data.get("title", "")).lower():
                        break
                except Exception:
                    pass
                time.sleep(0.04)
            type_res = _get_tool("type_text_tool")(raw_text, target_app=app)
            if type_res.success:
                return ToolResult(
                    True,
                    "open_and_type",
                    f"Opened {app.capitalize()} and typed '{raw_text}'.",
                    {"app": app, "text": raw_text, "open": open_res.to_dict(), "type": type_res.to_dict()},
                )
            return ToolResult(
                False,
                "open_and_type",
                f"Opened {app.capitalize()}, but could not type: {type_res.message}",
                {"app": app, "text": raw_text, "open": open_res.to_dict(), "type": type_res.to_dict()},
            )

    match = OPEN_APP_RE.match(question_cleaned)
    if match:
        app = cleanup_app_name(match.group("app"))
        if app and app not in {"help", "settings", "menu"}:
            normalized = normalize_app_name(app)
            # Check if it's a known desktop app first
            is_known_app = normalized in APP_PROTOCOLS or normalized in APP_NAME_ALIASES or normalized in SAFE_PROCESS_ALIASES
            if is_known_app:
                return _get_tool("open_app_tool")(app)
            if is_web_destination(app):
                if observation is None:
                    return None
                return _get_tool("open_web_destination_tool")(app)
            if not is_in_app_action(app) and looks_like_app_name(app):
                return _get_tool("open_app_tool")(app)

    return None

def _try_desktop_action(question: str) -> ToolResult | None:
    # List windows
    if LIST_WINDOWS_RE.match(question):
        return _get_tool("list_windows_tool")()

    # Inspect an app
    app_match = GET_APP_STATE_RE.match(question)
    if app_match:
        app = app_match.group("app")
        if app and looks_like_app_name(app):
            return _get_tool("get_app_state_tool")(app)

    # Click an element
    click_match = CLICK_ELEMENT_RE.match(question)
    if click_match:
        # Screen clicks require UI visual grounding and AI cursor movement (OmniParser/UIA/refs)
        # Return None to allow the full vision/autopilot pipeline to resolve coordinates and glide cursor.
        return None

    # Type text
    type_match = (
        TYPE_TEXT_IN_APP_RE.match(question)
        or TYPE_TEXT_TO_APP_RE.match(question)
        or TYPE_TEXT_RE.match(question)
    )
    if type_match:
        text = type_match.group("text")
        app = type_match.group("app") if "app" in type_match.groupdict() else None
        if text:
            cleaned_text = text.strip()
            # If app is a cell reference (e.g. "cell b1", "cell a1"), route directly to spreadsheet tool
            if app and re.match(r"^cell\s+[a-zA-Z]{1,3}\d+$", app.strip(), re.IGNORECASE):
                cell_ref = re.sub(r"^cell\s+", "", app.strip(), flags=re.IGNORECASE).upper()
                try:
                    from tools.spreadsheet_tool import execute_type_in_cell
                    sheet_res = execute_type_in_cell(cell_ref, cleaned_text)
                    return ToolResult(
                        sheet_res.get("success", True),
                        "spreadsheet_tool",
                        sheet_res.get("message", f"Typed '{cleaned_text}' in cell {cell_ref}."),
                        sheet_res,
                    )
                except Exception as exc:
                    LOGGER.debug("execute_type_in_cell in agent.py failed: %s", exc)

            # If user asks to type a number sequence like "1 to 9" or "from 1 to 9"
            range_match = re.match(r"^(?:from\s+)?(\d+)\s+to\s+(\d+)$", cleaned_text, re.IGNORECASE)
            if range_match:
                start_n, end_n = int(range_match.group(1)), int(range_match.group(2))
                if start_n <= end_n and (end_n - start_n) <= 100:
                    if app and any(k in app.lower() for k in ("sheet", "excel", "table")):
                        cleaned_text = "\t".join(str(i) for i in range(start_n, end_n + 1))
                    else:
                        cleaned_text = " ".join(str(i) for i in range(start_n, end_n + 1))

            return _get_tool("type_text_tool")(cleaned_text, target_app=app.strip() if app else None)

    return None

# Backward compatibility alias
_try_linux_action = _try_desktop_action


def cleanup_app_name(value: str) -> str:
    text = " ".join(value.strip().split())
    text = re.sub(r"\s+\b(app|application|only|just|window|please)$", "", text, flags=re.IGNORECASE).strip()
    return text


def wants_help_menu(question: str, observation: dict[str, Any] | None) -> bool:
    normalized = question.lower()
    if not any(phrase in normalized for phrase in {"open help", "help menu", "open the help"}):
        return False
    active_app = observation.get("active_app", {}) if isinstance(observation, dict) else {}
    process = str(active_app.get("process", "")).lower()
    app_context = str(observation.get("app_context", "")).lower() if isinstance(observation, dict) else ""
    return process in {"code.exe", "code"} or "shortcut: alt+h" in app_context

