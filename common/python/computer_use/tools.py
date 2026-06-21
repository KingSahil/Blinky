from __future__ import annotations

import json
import os
import re
import subprocess
import time
import webbrowser
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

WEB_DESTINATION_URLS = {
    "youtube": "https://www.youtube.com/",
    "you tube": "https://www.youtube.com/",
    "youtube music": "https://music.youtube.com/",
    "you tube music": "https://music.youtube.com/",
    "gmail": "https://mail.google.com/",
    "google": "https://www.google.com/",
    "google search": "https://www.google.com/",
    "google drive": "https://drive.google.com/",
    "google docs": "https://docs.google.com/document/",
    "google sheets": "https://docs.google.com/spreadsheets/",
    "google slides": "https://docs.google.com/presentation/",
    "whatsapp web": "https://web.whatsapp.com/",
    "facebook": "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
    "x": "https://x.com/",
    "twitter": "https://x.com/",
    "linkedin": "https://www.linkedin.com/",
    "reddit": "https://www.reddit.com/",
    "github": "https://github.com/",
    "chatgpt": "https://chatgpt.com/",
    "chat gpt": "https://chatgpt.com/",
}


def open_app_tool(app_name: str) -> ToolResult:
    try:
        from tools_win import open_app_tool_impl
        return open_app_tool_impl(app_name)
    except ImportError:
        return ToolResult(False, "open_app", "Opening desktop apps is currently supported on Windows only.", {"app_name": app_name})


def open_web_destination_tool(destination: str) -> ToolResult:
    normalized = normalize_web_destination(destination)
    url = WEB_DESTINATION_URLS.get(normalized)
    if not url and is_domain_like_destination(normalized):
        url = normalized if re.match(r"^https?://", normalized) else f"https://{normalized}"

    if not url:
        return ToolResult(
            False,
            "open_web_destination",
            f"I do not know a safe URL for '{destination}'.",
            {"destination": destination},
        )

    opened = webbrowser.open(url)
    if not opened:
        return ToolResult(
            False,
            "open_web_destination",
            f"Could not open {url} in the default browser.",
            {"destination": destination, "url": url},
        )

    return ToolResult(
        True,
        "open_web_destination",
        f"Opened {display_web_destination(destination)}.",
        {"destination": destination, "url": url},
    )


def shortcut_tool(shortcut: str) -> ToolResult:
    try:
        from tools_win import shortcut_tool_impl
        return shortcut_tool_impl(shortcut)
    except ImportError:
        return ToolResult(False, "shortcut", "Keyboard shortcuts are currently supported on Windows only.", {"shortcut": shortcut})


def find_start_app(app_name: str) -> dict[str, Any] | None:
    try:
        from tools_win import find_start_app_impl
        return find_start_app_impl(app_name)
    except ImportError:
        return None


def open_app_via_windows_search(app_name: str) -> ToolResult:
    try:
        from tools_win import open_app_via_windows_search_impl
        return open_app_via_windows_search_impl(app_name)
    except ImportError:
        return ToolResult(False, "open_app", "Windows Search fallback is only available on Windows.", {"app_name": app_name})


def find_windows_search_result(app_name: str) -> dict[str, Any] | None:
    try:
        from tools_win import find_windows_search_result_impl
        return find_windows_search_result_impl(app_name)
    except ImportError:
        return None


def click_item_center(item: dict[str, Any]) -> None:
    from pywinauto.mouse import click
    x = int(float(item.get("x") or 0) + float(item.get("width") or 0) / 2)
    y = int(float(item.get("y") or 0) + float(item.get("height") or 0) / 2)
    click(button="left", coords=(x, y))


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


def normalize_web_destination(value: str) -> str:
    text = " ".join(str(value).strip().lower().split())
    text = re.sub(r"\b(app|application|website|site|page|please|for me)\b", " ", text)
    text = re.sub(r"[^a-z0-9 .:/_-]", "", text)
    return " ".join(text.split()).strip(" ._-")


def is_domain_like_destination(value: str) -> bool:
    return bool(re.match(r"^(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+/?$", value))


def display_web_destination(value: str) -> str:
    cleaned = " ".join(str(value).strip().split()).strip()
    return cleaned or "the website"


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


def play_spotify_track_tool(song_name: str) -> ToolResult:
    import asyncio

    if os.name != "nt":
        return ToolResult(
            False,
            "play_spotify",
            "Playing Spotify tracks via URI is currently supported on Windows only.",
            {"song_name": song_name},
        )

    try:
        import threading
        from concurrent.futures import Future

        future: Future[str | None] = Future()

        def run_in_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(resolve_spotify_track_uri(song_name))
                future.set_result(result)
            except Exception as ex:
                future.set_exception(ex)
            finally:
                loop.close()

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        track_uri = future.result()

        if not track_uri:
            return ToolResult(
                False,
                "play_spotify",
                f"Could not find track '{song_name}' on Spotify.",
                {"song_name": song_name},
            )

        os.startfile(track_uri)
        return ToolResult(
            True,
            "play_spotify",
            f"Playing '{song_name}' in Spotify.",
            {"song_name": song_name, "track_uri": track_uri},
        )
    except Exception as e:
        LOGGER.exception("Error in play_spotify_track_tool")
        return ToolResult(
            False,
            "play_spotify",
            f"Error playing '{song_name}' on Spotify: {str(e)}",
            {"song_name": song_name, "error": str(e)},
        )


def clean_song_query(query: str) -> str:
    query = " ".join(query.strip().split())

    strip_words = {
        "any", "latest", "new", "newest", "some", "a", "the", "recent", "trending",
        "popular", "song", "track", "music", "artist", "singer", "playlist", "by"
    }

    words = query.split()
    changed = True
    while changed and words:
        changed = False
        if words[0].lower() in strip_words:
            words.pop(0)
            changed = True
        elif words and words[-1].lower() in strip_words:
            words.pop()
            changed = True

    cleaned = " ".join(words).strip()
    return cleaned if cleaned else query


async def resolve_spotify_track_uri(song_name: str) -> str | None:
    from wil.searxng_client import SearXNGClient
    from wil.http_fetcher import fetch_html
    import urllib.parse

    cleaned_query = clean_song_query(song_name)
    LOGGER.info(f"Resolving Spotify URI for '{song_name}' (cleaned: '{cleaned_query}')")

    queries = [
        f"site:open.spotify.com/track {cleaned_query}",
        f"{cleaned_query} spotify track"
    ]

    try:
        client = SearXNGClient()
        for q in queries:
            results = await client.search_category(q, category="general", limit=5)
            for r in results:
                url = r.get("url", "")
                if "open.spotify.com/track/" in url:
                    match = re.search(r"track/([a-zA-Z0-9]+)", url)
                    if match:
                        return f"spotify:track:{match.group(1)}"
    except Exception as e:
        LOGGER.warning(f"SearXNG Spotify search failed: {e}")

    for q in queries:
        try:
            query_encoded = urllib.parse.quote(q)
            url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
            html = await fetch_html(url)
            if html:
                unquoted_html = urllib.parse.unquote(html)
                matches = re.findall(r"open\.spotify\.com/track/([a-zA-Z0-9]+)", unquoted_html)
                if matches:
                    return f"spotify:track:{matches[0]}"
        except Exception as e:
            LOGGER.warning(f"DuckDuckGo fallback search for '{q}' failed: {e}")

    return None
