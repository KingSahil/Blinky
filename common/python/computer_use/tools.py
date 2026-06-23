from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use")

IS_LINUX = platform.system() == "Linux"

_WAYLAND_VISION_AVAILABLE = False
try:
    from wayland_vision import capture_window_crop, get_screen_scale
    _WAYLAND_VISION_AVAILABLE = True
except ImportError:
    pass


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


def _to_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _is_relative_coordinate(coords: dict[str, Any]) -> bool:
    if coords.get("source") == "ocr":
        return True
    if "absolute_bounds" in coords:
        return False
    if "x" in coords and "y" in coords:
        if "source" not in coords:
            return True
    return False


def translate_relative_to_absolute(
    ocr_coords: dict[str, Any],
    window_bounds: dict[str, Any] | None,
    scale: float = 1.0,
) -> dict[str, Any]:
    result = dict(ocr_coords)

    if window_bounds is None:
        LOGGER.warning("translate_relative_to_absolute: window_bounds is None, returning coords unchanged")
        return result

    dx = _to_int(ocr_coords.get("x", 0))
    dy = _to_int(ocr_coords.get("y", 0))

    if _WAYLAND_VISION_AVAILABLE:
        from wayland_vision import translate_to_absolute
        abs_x, abs_y = translate_to_absolute(window_bounds, dx, dy, scale)
    else:
        abs_x = int((window_bounds["x"] + dx) * scale)
        abs_y = int((window_bounds["y"] + dy) * scale)

    if abs_x < 0:
        abs_x = 0
    if abs_y < 0:
        abs_y = 0

    result["absolute_bounds"] = {
        "x": abs_x,
        "y": abs_y,
        "width": _to_int(ocr_coords.get("width", 0)),
        "height": _to_int(ocr_coords.get("height", 0)),
    }

    return result


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


# ---------------------------------------------------------------------------
# Linux desktop automation tools (via computer-use-linux MCP)
# ---------------------------------------------------------------------------

_GRIM_AVAILABLE: bool | None = None


def _check_grim_available() -> bool:
    global _GRIM_AVAILABLE
    if _GRIM_AVAILABLE is not None:
        return _GRIM_AVAILABLE
    try:
        import subprocess
        result = subprocess.run(["which", "grim"], capture_output=True, timeout=2)
        _GRIM_AVAILABLE = result.returncode == 0
    except Exception:
        _GRIM_AVAILABLE = False
    return _GRIM_AVAILABLE


def _detect_desktop_session() -> str:
    session = os.environ.get("XDG_SESSION_TYPE", "").lower().strip()
    grim_ok = _check_grim_available()
    LOGGER.info("Desktop session: XDG_SESSION_TYPE=%s, grim_available=%s", session, grim_ok)
    if session == "wayland" and grim_ok:
        return "wayland"
    return "x11"


def _get_linux_mcp():
    try:
        from computer_use.linux_mcp import get_client
        return get_client()
    except Exception as e:
        LOGGER.warning("Linux MCP client unavailable: %s", e)
        return None


def list_windows_tool() -> ToolResult:
    if not IS_LINUX:
        return ToolResult(False, "list_windows", "Desktop window listing is supported on Linux only.", {})

    try:
        from computer_use.linux_mcp import list_windows
        windows = list_windows()
        return ToolResult(
            True,
            "list_windows",
            f"Found {len(windows)} windows.",
            {"windows": windows, "count": len(windows)},
        )
    except Exception as e:
        LOGGER.exception("list_windows_tool failed")
        return ToolResult(False, "list_windows", str(e), {})


def get_app_state_tool(app_name: str) -> ToolResult:
    if not IS_LINUX:
        return ToolResult(False, "get_app_state", "Desktop app inspection is supported on Linux only.", {"app_name": app_name})

    try:
        from computer_use.linux_mcp import get_app_state
        state = get_app_state(app_name=app_name, max_nodes=200, max_depth=4)
        elements = state.get("elements", [])
        windows = state.get("windows", [])
        return ToolResult(
            True,
            "get_app_state",
            f"App '{app_name}': {len(elements)} elements, {len(windows)} windows.",
            {
                "app_name": app_name,
                "elements": elements,
                "windows": windows,
                "element_count": len(elements),
                "window_count": len(windows),
            },
        )
    except Exception as e:
        LOGGER.exception("get_app_state_tool failed")
        return ToolResult(False, "get_app_state", str(e), {"app_name": app_name})


def click_element_tool(
    index: int | None = None,
    role: str | None = None,
    name: str | None = None,
    x: int | None = None,
    y: int | None = None,
) -> ToolResult:
    if not IS_LINUX:
        return ToolResult(False, "click_element", "Desktop clicking is supported on Linux only.", {})

    try:
        from computer_use.linux_mcp import click_element, _check_ok
        result = click_element(index=index, role=role, name=name, x=x, y=y)
        ok = _check_ok(result)
        return ToolResult(
            ok,
            "click_element",
            "Click executed successfully." if ok else f"Click failed: {result.get('message', 'unknown')}",
            {"result": result, "index": index, "role": role, "name": name},
        )
    except Exception as e:
        LOGGER.exception("click_element_tool failed")
        return ToolResult(False, "click_element", str(e), {})


def type_text_tool(text: str, target_app: str | None = None) -> ToolResult:
    if not IS_LINUX:
        return ToolResult(False, "type_text", "Desktop typing is supported on Linux only.", {"text": text})

    try:
        from computer_use.linux_mcp import type_text, _check_ok
        result = type_text(text, target_app=target_app)
        ok = _check_ok(result)
        return ToolResult(
            ok,
            "type_text",
            f"Typed '{text}' successfully." if ok else f"Failed to type: {result.get('message', 'unknown')}",
            {"text": text, "target_app": target_app, "result": result},
        )
    except Exception as e:
        LOGGER.exception("type_text_tool failed")
        return ToolResult(False, "type_text", str(e), {"text": text})


def press_key_tool(key: str, target_app: str | None = None) -> ToolResult:
    if not IS_LINUX:
        return ToolResult(False, "press_key", "Desktop key presses are supported on Linux only.", {"key": key})

    try:
        from computer_use.linux_mcp import press_key, _check_ok
        result = press_key(key, target_app=target_app)
        ok = _check_ok(result)
        return ToolResult(
            ok,
            "press_key",
            f"Pressed '{key}' successfully." if ok else f"Failed to press '{key}': {result.get('message', 'unknown')}",
            {"key": key, "target_app": target_app, "result": result},
        )
    except Exception as e:
        LOGGER.exception("press_key_tool failed")
        return ToolResult(False, "press_key", str(e), {"key": key})


def mouse_tool(
    action: str,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    scroll_amount: int = 3,
) -> ToolResult:
    """Virtual mouse control via ydotool.

    Actions:
      move    — move cursor to absolute (x, y)
      click   — move to (x, y) and click
      scroll  — scroll at current position (scroll_amount: positive=down, negative=up)
    """
    if not IS_LINUX:
        return ToolResult(False, "mouse", "Mouse control is supported on Linux only.", {})

    try:
        import subprocess

        # Normalize common action aliases
        _action_aliases = {
            "left_click": "click", "right_click": "click", "double_click": "click",
            "leftclick": "click", "rightclick": "click", "middle_click": "click",
        }
        if action in _action_aliases:
            if action in ("right_click", "rightclick"):
                button = "right"
            elif action in ("middle_click",):
                button = "middle"
            action = _action_aliases[action]

        if action == "move":
            if x is None or y is None:
                return ToolResult(False, "mouse", "move requires x and y coordinates.", {})
            vm = VirtualMouse.get_instance()
            vm.move(int(x), int(y))
            LOGGER.info("Mouse move: x=%d, y=%d (via VirtualMouse)", int(x), int(y))
            return ToolResult(True, "mouse", f"Mouse moved to ({int(x)}, {int(y)}).", {"x": x, "y": y, "action": "move"})

        elif action == "click":
            if x is None or y is None:
                return ToolResult(False, "mouse", "click requires x and y coordinates.", {})
            _virtual_mouse_click(int(x), int(y), button)
            return ToolResult(True, "mouse", f"Clicked ({int(x)}, {int(y)}) with {button}.", {"x": x, "y": y, "button": button, "action": "click"})

            # ── Visual click indicator: crosshair pattern ──
            _show_click_crosshair(int(x), int(y))

            # ── Debug screenshot after click ──
            try:
                raw_path = capture_screenshot()
                if raw_path:
                    label = f"click_{int(x)}x{int(y)}_{int(time.time()*1000)}"
                    debug_path = str(Path(raw_path).parent / f"debug_{label}.png")
                    os.rename(raw_path, debug_path)
                    LOGGER.info("Click debug screenshot: %s", debug_path)
            except Exception:
                pass

            return ToolResult(True, "mouse", f"Clicked ({int(x)}, {int(y)}) with {button}.", {"x": x, "y": y, "button": button, "action": "click"})

        elif action == "scroll":
            direction = "scroll-down" if scroll_amount > 0 else "scroll-up"
            amount = abs(scroll_amount)
            vm = VirtualMouse.get_instance()
            vm.scroll(scroll_amount)
            LOGGER.info("Mouse scroll: direction=%s, amount=%d (via VirtualMouse)", direction, amount)
            return ToolResult(True, "mouse", f"Scrolled {direction} by {amount}.", {"direction": direction, "amount": amount, "action": "scroll"})

        else:
            return ToolResult(False, "mouse", f"Unknown mouse action: {action}. Use move, click, or scroll.", {})

    except Exception as e:
        LOGGER.exception("mouse_tool failed")
        return ToolResult(False, "mouse", str(e), {})


_SCREENSHOT_COUNTER = 0


def _show_click_crosshair(x: int, y: int) -> None:
    """Draw a visible crosshair at (x, y) using the virtual mouse for visual debugging.
    Returns the cursor to (x, y) after the pattern completes (~500ms total)."""
    try:
        vm = VirtualMouse.get_instance()
        pattern = [
            (18,0), (0,0), (-18,0), (0,0), (0,18), (0,0), (0,-18), (0,0),
        ]
        for dx, dy in pattern:
            vm.move(x + dx, y + dy)
            time.sleep(0.06)
    except Exception:
        pass


def _screenshot_temp_dir() -> Path:
    d = Path("tmp") / "grim_captures"
    try:
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o700)
    except Exception:
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / "blinky_grim"
        temp_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.warning("Falling back to tempfile.gettempdir for grim captures: %s", temp_dir)
        return temp_dir
    return d


def _cleanup_old_screenshots(max_age: int = 300, max_files: int = 50) -> None:
    """Remove grim capture files older than max_age seconds or beyond max_files."""
    try:
        d = _screenshot_temp_dir()
        files = sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[max_files:]:
            f.unlink(missing_ok=True)
        cutoff = time.time() - max_age
        for f in files:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def screenshot_tool() -> ToolResult:
    if not IS_LINUX:
        return ToolResult(False, "screenshot", "Desktop screenshots are supported on Linux only.", {})

    global _SCREENSHOT_COUNTER
    _SCREENSHOT_COUNTER += 1
    mode = os.environ.get("BLINKY_SCREENSHOT_MODE", "ocr").strip().lower()

    ocr_items: list[dict[str, Any]] = []
    window_bounds: dict[str, Any] | None = None
    image_path: str | None = None
    has_vision: bool = False

    try:
        from ai.client import has_vision_capability
        has_vision = has_vision_capability()
    except Exception:
        pass

    # In legacy mode, use MCP screenshot directly
    if mode == "legacy":
        try:
            from computer_use.linux_mcp import screenshot
            result = screenshot()
            # Decode base64 image data from MCP response
            content_list = result.get("content", []) if isinstance(result, dict) else []
            decoded_path = None
            for item in content_list:
                if isinstance(item, dict) and item.get("type") == "image" and item.get("data"):
                    import base64 as b64
                    _cleanup_old_screenshots()
                    ts = int(time.time() * 1000)
                    out_path = _screenshot_temp_dir() / f"mcp_legacy_{ts}_{_SCREENSHOT_COUNTER}.png"
                    out_path.write_bytes(b64.b64decode(item["data"]))
                    decoded_path = str(out_path.resolve())
                    break
            return ToolResult(
                True,
                "screenshot",
                "Screenshot captured.",
                {"result": result, "ocr_items": [], "window_bounds": None, "has_vision": has_vision,
                 "image_path": decoded_path},
            )
        except Exception as e:
            LOGGER.exception("screenshot_tool failed")
            return ToolResult(False, "screenshot", str(e), {})

    # OCR mode: grim + OCR
    try:
        session = _detect_desktop_session()
        LOGGER.info("Screenshot OCR mode: session=%s, wayland_vision=%s", session, _WAYLAND_VISION_AVAILABLE)
        bounds: dict | None = None

        # Get focused window bounds
        if session == "wayland" and _WAYLAND_VISION_AVAILABLE:
            try:
                from computer_use.linux_mcp import get_focused_window_bounds
                bounds = get_focused_window_bounds()
                LOGGER.info("Focused window bounds: %s", bounds)
            except Exception as e:
                LOGGER.warning("get_focused_window_bounds failed: %s", e)
                pass

        # Validate bounds
        valid_bounds = False
        if bounds and isinstance(bounds, dict):
            x_v = bounds.get("x")
            y_v = bounds.get("y")
            w_v = bounds.get("width")
            h_v = bounds.get("height")
            if (isinstance(x_v, (int, float)) and isinstance(y_v, (int, float))
                    and isinstance(w_v, (int, float)) and isinstance(h_v, (int, float))
                    and int(x_v) >= 0 and int(y_v) >= 0 and int(w_v) > 0 and int(h_v) > 0):
                valid_bounds = True
        LOGGER.info("Bounds validation: valid_bounds=%s", valid_bounds)

        # Attempt grim capture
        grim_succeeded = False
        if session == "wayland" and _WAYLAND_VISION_AVAILABLE and valid_bounds:
            try:
                _cleanup_old_screenshots()
                ts = int(time.time() * 1000)
                out_path = _screenshot_temp_dir() / f"grim_{ts}_{_SCREENSHOT_COUNTER}.png"
                _ = capture_window_crop(
                    {"x": int(bounds["x"]), "y": int(bounds["y"]),
                     "width": int(bounds["width"]), "height": int(bounds["height"])},
                    str(out_path),
                )
                if out_path.exists():
                    image_path = str(out_path.resolve())
                    grim_succeeded = True
                    window_bounds = {
                        "x": int(bounds["x"]), "y": int(bounds["y"]),
                        "width": int(bounds["width"]), "height": int(bounds["height"]),
                    }
            except Exception:
                LOGGER.exception("grim capture failed, falling back to MCP screenshot")
                pass

        # Direct grim subprocess fallback (no wayland_vision module needed)
        if not grim_succeeded and session == "wayland" and _check_grim_available():
            try:
                _cleanup_old_screenshots()
                ts = int(time.time() * 1000)
                out_path = _screenshot_temp_dir() / f"grim_{ts}_{_SCREENSHOT_COUNTER}.png"
                import subprocess as _sp
                _sp.run(["grim", str(out_path)], capture_output=True, timeout=10)
                if out_path.exists():
                    image_path = str(out_path.resolve())
                    grim_succeeded = True
                    from PIL import Image
                    with Image.open(image_path) as _img:
                        _fw, _fh = _img.size
                    window_bounds = {"x": 0, "y": 0, "width": _fw, "height": _fh}
                    LOGGER.info("Direct grim capture: %s (%dx%d)", image_path, _fw, _fh)
            except Exception:
                LOGGER.exception("Direct grim capture failed")
                pass

        # If all grim attempts failed, mark grim as unavailable so we don't retry
        if not grim_succeeded:
            global _GRIM_AVAILABLE
            _GRIM_AVAILABLE = False

        # Fallback to MCP screenshot if grim failed
        if not grim_succeeded:
            LOGGER.info("Grim capture not used, falling back to MCP screenshot")
            try:
                from computer_use.linux_mcp import screenshot
                result = screenshot()
                LOGGER.info("MCP screenshot result keys: %s", list(result.keys()) if isinstance(result, dict) else type(result))

                # MCP returns {"content": [{"type": "image", "data": "<base64>"}], "isError": false}
                content_list = result.get("content", []) if isinstance(result, dict) else []
                img_data = None
                for item in content_list:
                    if isinstance(item, dict) and item.get("type") == "image" and item.get("data"):
                        img_data = item["data"]
                        break

                if img_data:
                    import base64 as b64
                    _cleanup_old_screenshots()
                    ts = int(time.time() * 1000)
                    out_path = _screenshot_temp_dir() / f"mcp_{ts}_{_SCREENSHOT_COUNTER}.png"
                    out_path.write_bytes(b64.b64decode(img_data))
                    image_path = str(out_path.resolve())
                    LOGGER.info("MCP screenshot saved to: %s", image_path)
                else:
                    LOGGER.warning("MCP screenshot: no image data in content list")
            except Exception:
                LOGGER.exception("MCP screenshot fallback failed")
                return ToolResult(
                    True, "screenshot", "Screenshot captured (no image available).",
                    {"ocr_items": [], "window_bounds": None, "has_vision": has_vision,
                     "image_path": None},
                )

        # Run OCR on captured image
        if image_path:
            try:
                from ocr import extract_visible_text
                items = extract_visible_text(Path(image_path))
                if items:
                    ocr_items = items
                    # Scale OCR coords from image space to screen space if mismatch
                    try:
                        from PIL import Image
                        with Image.open(image_path) as _img:
                            img_w, img_h = _img.size
                        sw, sh = _get_screen_dimensions()
                        if (img_w, img_h) != (sw, sh) and img_w > 0 and img_h > 0:
                            sx = sw / img_w
                            sy = sh / img_h
                            LOGGER.info("Scaling OCR coords: img=%dx%d screen=%dx%d factors=(%.4f, %.4f)",
                                       img_w, img_h, sw, sh, sx, sy)
                            for item in ocr_items:
                                if "x" in item:
                                    item["x"] = int(item["x"] * sx)
                                if "y" in item:
                                    item["y"] = int(item["y"] * sy)
                                if "width" in item:
                                    item["width"] = int(item["width"] * sx)
                                if "height" in item:
                                    item["height"] = int(item["height"] * sy)
                    except Exception:
                        LOGGER.exception("OCR coordinate scaling failed")
            except Exception:
                LOGGER.exception("OCR extraction failed, returning empty ocr_items")
                ocr_items = []

        return ToolResult(
            True,
            "screenshot",
            f"Screenshot captured. OCR items: {len(ocr_items)}.",
            {
                "image_path": image_path,
                "ocr_items": ocr_items,
                "window_bounds": window_bounds,
                "has_vision": has_vision,
            },
        )

    except Exception as e:
        LOGGER.exception("screenshot_tool(ocr) failed")
        return ToolResult(
            True, "screenshot", f"Screenshot captured (OCR unavailable: {e})",
            {"ocr_items": [], "window_bounds": None, "has_vision": has_vision, "image_path": None},
        )


def open_app_tool_linux(app_name: str) -> ToolResult:
    """Open a desktop application by name on Linux using subprocess.Popen."""
    if not IS_LINUX:
        return ToolResult(False, "open_app", "App launching is supported on Linux only.", {"app_name": app_name})

    app_lower = app_name.lower().strip()
    binary_map = {
        "calculator": "gnome-calculator",
        "gnome calculator": "gnome-calculator",
        "calc": "gnome-calculator",
        "firefox": "firefox",
        "chrome": "google-chrome",
        "google chrome": "google-chrome",
        "chromium": "chromium-browser",
        "terminal": "konsole",
        "konsole": "konsole",
        "gnome terminal": "gnome-terminal",
        "files": "dolphin",
        "dolphin": "dolphin",
        "nautilus": "nautilus",
        "settings": "systemsettings",
        "system settings": "systemsettings",
        "text editor": "kate",
        "kate": "kate",
        "gedit": "gedit",
        "code": "code",
        "vscode": "code",
        "visual studio code": "code",
        "discord": "flatpak run org.equicord.equibop",
        "equibop": "flatpak run org.equicord.equibop",
    }

    binary = binary_map.get(app_lower, app_lower.replace(" ", "-"))

    try:
        env = os.environ.copy()
        env.setdefault("GTK_A11Y", "atspi")
        env.setdefault("AT_SPI_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/at-spi/bus_0")
        cmd = binary.split() if " " in binary else [binary]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        import time
        time.sleep(0.8)
        return ToolResult(
            True,
            "open_app",
            f"Launched '{app_name}' (binary: {binary}).",
            {"app_name": app_name, "binary": binary},
        )
    except FileNotFoundError:
        # Try via KRunner-like approach: use the name directly
        try:
            subprocess.Popen(
                app_name.split() if " " in app_name else [app_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
            return ToolResult(
                True,
                "open_app",
                f"Launched '{app_name}' directly.",
                {"app_name": app_name},
            )
        except Exception as e:
            return ToolResult(False, "open_app", f"Cannot find or launch '{app_name}': {e}", {"app_name": app_name})
    except Exception as e:
        return ToolResult(False, "open_app", f"Failed to launch '{app_name}': {e}", {"app_name": app_name})


def capture_screenshot() -> str | None:
    """Take a screenshot and return the image path, or None on failure.

    Reuses the MCP base64 decode logic from screenshot_tool fallback.
    Never raises — logs and returns None on failure.
    """
    try:
        from computer_use.linux_mcp import screenshot
        result = screenshot()
        content_list = result.get("content", []) if isinstance(result, dict) else []
        for item in content_list:
            if isinstance(item, dict) and item.get("type") == "image" and item.get("data"):
                import base64 as b64
                _cleanup_old_screenshots()
                ts = int(time.time() * 1000)
                out_path = _screenshot_temp_dir() / f"capture_{ts}_{_SCREENSHOT_COUNTER}.png"
                out_path.write_bytes(b64.b64decode(item["data"]))
                return str(out_path.resolve())
        # Try grim if MCP didn't return image data
        session = _detect_desktop_session()
        if session == "wayland" and _WAYLAND_VISION_AVAILABLE:
            try:
                from computer_use.linux_mcp import get_focused_window_bounds
                from wayland_vision import capture_window_crop
                bounds = get_focused_window_bounds()
                if bounds and isinstance(bounds, dict):
                    ts = int(time.time() * 1000)
                    out_path = _screenshot_temp_dir() / f"capture_grim_{ts}_{_SCREENSHOT_COUNTER}.png"
                    _ = capture_window_crop(
                        {"x": int(bounds["x"]), "y": int(bounds["y"]),
                         "width": int(bounds["width"]), "height": int(bounds["height"])},
                        str(out_path),
                    )
                    if out_path.exists():
                        return str(out_path.resolve())
            except Exception:
                pass
        LOGGER.warning("capture_screenshot: no image data from MCP or grim")
        return None
    except Exception:
        LOGGER.exception("capture_screenshot failed")
        return None


def checksum_frame(image_path: str) -> str | None:
    """Compute MD5 hash of raw pixel data from a PNG image.

    Returns hex digest string, or None if file doesn't exist or can't be read.
    """
    try:
        from PIL import Image
    except ImportError:
        LOGGER.warning("checksum_frame: PIL not available")
        return None

    try:
        with Image.open(image_path) as img:
            return hashlib.md5(img.tobytes()).hexdigest()
    except FileNotFoundError:
        LOGGER.warning("checksum_frame: file not found: %s", image_path)
        return None
    except Exception:
        LOGGER.exception("checksum_frame failed for: %s", image_path)
        return None


_VIRTUAL_MOUSE: object | None = None
_VM_SCREEN_W: int = 2560
_VM_SCREEN_H: int = 1440


class VirtualMouse:
    """Dedicated uinput virtual mouse device for reliable input injection.

    Creates a second virtual mouse device independent of ydotoold/MCP bridge.
    Uses absolute positioning (ABS_X/ABS_Y) with a touchscreen-like interface
    that KWin/libinput recognizes as a pointing device.

    Singleton — one device shared across all calls.
    """

    _instance: VirtualMouse | None = None

    def __init__(self, screen_w: int = 2560, screen_h: int = 1440) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._ui: Any = None
        self.e: Any = None
        self._create_device()

    def _create_device(self) -> None:
        try:
            from evdev import UInput, ecodes as e, AbsInfo
            self.e = e
            self._ui = UInput(
                {
                    e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
                    e.EV_ABS: [
                        (e.ABS_X, AbsInfo(value=self.screen_w // 2, min=0, max=self.screen_w, fuzz=0, flat=0, resolution=100)),
                        (e.ABS_Y, AbsInfo(value=self.screen_h // 2, min=0, max=self.screen_h, fuzz=0, flat=0, resolution=100)),
                    ],
                    e.EV_REL: [e.REL_WHEEL, e.REL_HWHEEL],
                },
                name="jarvis-virt-mouse",
                version=0x01,
            )
            LOGGER.info("VirtualMouse created: %s", self._ui.device)
        except Exception:
            LOGGER.exception("Failed to create VirtualMouse uinput device")
            self._ui = None

    def move(self, x: int, y: int) -> None:
        if self._ui is None or self.e is None:
            return
        x = max(0, min(x, self.screen_w))
        y = max(0, min(y, self.screen_h))
        self._ui.write(self.e.EV_ABS, self.e.ABS_X, x)
        self._ui.write(self.e.EV_ABS, self.e.ABS_Y, y)
        self._ui.syn()

    def scroll(self, amount: int) -> None:
        if self._ui is None or self.e is None:
            return
        direction = -1 if amount > 0 else 1
        clicks = abs(amount)
        for _ in range(clicks):
            self._ui.write(self.e.EV_REL, self.e.REL_WHEEL, direction)
            self._ui.syn()
            time.sleep(0.01)

    def click(self, x: int, y: int, button: str = "left") -> bool:
        if self._ui is None or self.e is None:
            return False
        try:
            self.move(x, y)
            time.sleep(0.03)
            btn_map = {"left": self.e.BTN_LEFT, "right": self.e.BTN_RIGHT, "middle": self.e.BTN_MIDDLE}
            btn = btn_map.get(button, self.e.BTN_LEFT)
            self._ui.write(self.e.EV_KEY, btn, 1)
            self._ui.syn()
            time.sleep(0.03)
            self._ui.write(self.e.EV_KEY, btn, 0)
            self._ui.syn()
            return True
        except Exception:
            LOGGER.exception("VirtualMouse.click failed")
            return False

    def close(self) -> None:
        if self._ui is not None:
            try:
                self._ui.close()
            except Exception:
                pass
            self._ui = None

    @classmethod
    def get_instance(cls) -> VirtualMouse:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def _get_screen_dimensions() -> tuple[int, int]:
    """Get physical screen dimensions in pixels.

    Tries: xrandr → focused window bounds → 1920×1080 fallback.
    """
    # 1. xrandr gives actual display resolution (most reliable)
    try:
        import subprocess
        r = subprocess.run(["xrandr"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if " connected " in line and "x" in line:
                    parts = line.strip().split()
                    for p in parts:
                        if "x" in p and "+" in p and p.replace("x", "").replace("+", "").isdigit():
                            res = p.split("+")[0]
                            w_str, h_str = res.split("x", 1)
                            return int(w_str), int(h_str)
    except Exception:
        pass

    # 2. Fallback: focused window bounds
    try:
        from computer_use.linux_mcp import get_focused_window_bounds
        bounds = get_focused_window_bounds()
        if bounds and isinstance(bounds, dict):
            w = bounds.get("width") or 1920
            h = bounds.get("height") or 1080
            return int(w), int(h)
    except Exception:
        pass
    return 1920, 1080


def _virtual_mouse_click(x: int, y: int, button: str = "left") -> None:
    """Click at (x, y) using the dedicated virtual mouse device.

    Falls back to MCP bridge click → ydotool if uinput device creation fails.
    Shows crosshair overlay and saves debug screenshot after success.
    """
    sw, sh = _get_screen_dimensions()

    global _VIRTUAL_MOUSE, _VM_SCREEN_W, _VM_SCREEN_H
    if (sw, sh) != (_VM_SCREEN_W, _VM_SCREEN_H):
        _VM_SCREEN_W, _VM_SCREEN_H = sw, sh
        if VirtualMouse._instance is not None:
            VirtualMouse._instance.close()
            VirtualMouse._instance = None
        _VIRTUAL_MOUSE = None

    vm = VirtualMouse.get_instance()

    success = vm.click(x, y, button)
    if not success:
        LOGGER.warning("VirtualMouse click failed, falling back to MCP bridge")
        try:
            from computer_use.linux_mcp import get_client
            mcp_client = get_client()
            mcp_client.call_tool("click", {"x": x, "y": y})
        except Exception as mcp_err:
            LOGGER.warning("MCP bridge fallback also failed: %s", mcp_err)
            import subprocess as _sp
            _sp.run(["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)], capture_output=True, timeout=5)
            time.sleep(0.05)
            _sp.run(["ydotool", "click", "0xC0"], capture_output=True, timeout=5)

    LOGGER.info("Mouse click: x=%d, y=%d, button=%s (via VirtualMouse)", x, y, button)

    _show_click_crosshair(x, y)

    try:
        raw_path = capture_screenshot()
        if raw_path:
            label = f"click_{x}x{y}_{int(time.time()*1000)}"
            debug_path = str(Path(raw_path).parent / f"debug_{label}.png")
            os.rename(raw_path, debug_path)
            LOGGER.info("Click debug screenshot: %s", debug_path)
    except Exception:
        pass
