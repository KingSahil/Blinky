"""
Windows-Use Engine for Blinky.

Integrates Jeomon/Windows-Use UI Automation and agentic capabilities into Blinky.
Provides:
1. Sub-second deterministic fast paths for common compound desktop operations
   (e.g. "open notepad and create new tab and type hello world").
2. Ultra-fast LLM agent loop backed by Groq (qwen/qwen3.8-27b) or Gemini (gemini-3.8-flash)
   using native Windows UIA tree parsing with zero vision overhead.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Any

LOGGER = logging.getLogger("blinky.computer_use.windows_use")

# Separator helpers
SEP_OPT = r"(?:\s*(?:and\s+then|and|then|,)\s*|\s)*"

# Keyword atoms
_NP        = r"(?:open|launch|start)\s+(?:the\s+)?notepad"   # 'open notepad'
_NP_BARE   = r"(?:the\s+)?notepad"                            # bare 'notepad'
_NP_SUFFIX = r"(?:\s+(?:app|application))?"                   # optional ' app'
_TAB       = r"(?:create|open|add)\s+(?:a\s+)?(?:new\s+)?tab" # 'create a new tab'
_WRITE     = r"(?:type|write|enter|input|put)"                 # typing verb
_TXT_SKIP  = r"(?:(?:the|some|a)\s+)?(?:text\s+|words?\s+)?"  # filler before text
_END_IT    = r"(?:\s+(?:in|into|on)\s+it)?"                   # optional 'in it'

# 1. Compound Notepad: new tab + type
# Covers: "open notepad and create a new tab and type X"
#         "notepad create new tab and write X"
#         "in notepad create a new tab then type X"
#         "create a new tab in notepad and type X"
NOTEPAD_TAB_TYPE_RES = [
    # "open notepad in [a] new tab and write TEXT"
    # This is a common natural phrasing for opening Notepad and creating a
    # document tab; without this guard, "new tab" can pull the request toward
    # browser automation before the Notepad target is considered.
    re.compile(
        rf"^{_NP}{_NP_SUFFIX}{SEP_OPT}in\s+(?:a\s+)?(?:new\s+)?tab{SEP_OPT}{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?){_END_IT}$",
        re.IGNORECASE,
    ),
    # "open notepad [sep] create [a] [new] tab [sep] type TEXT"
    re.compile(
        rf"^{_NP}{_NP_SUFFIX}{SEP_OPT}{_TAB}(?:\s+in\s+notepad)?{SEP_OPT}{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?){_END_IT}$",
        re.IGNORECASE,
    ),
    # "notepad [sep] create [a] [new] tab [sep] type TEXT"
    re.compile(
        rf"^{_NP_BARE}{_NP_SUFFIX}{SEP_OPT}{_TAB}(?:\s+in\s+notepad)?{SEP_OPT}{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?){_END_IT}$",
        re.IGNORECASE,
    ),
    # "in/on notepad create [a] [new] tab [sep] type TEXT"
    re.compile(
        rf"^(?:in|on)\s+notepad\s*,?\s*{_TAB}{SEP_OPT}{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?){_END_IT}$",
        re.IGNORECASE,
    ),
    # "create [a] [new] tab in notepad [sep] type TEXT"
    re.compile(
        rf"^{_TAB}\s+in\s+notepad{SEP_OPT}{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?){_END_IT}$",
        re.IGNORECASE,
    ),
    # "type TEXT in [a] [new] tab in notepad"
    re.compile(
        rf"^{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?)\s+in\s+(?:a\s+)?(?:new\s+)?tab\s+in\s+notepad$",
        re.IGNORECASE,
    ),
    # "in notepad type TEXT in [a] [new] tab"
    re.compile(
        rf"^in\s+notepad\s*,?\s*{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?)\s+in\s+(?:a\s+)?(?:new\s+)?tab$",
        re.IGNORECASE,
    ),
]

# 2. Compound Notepad: open & type directly (no new tab)
# Covers: "open notepad and type X", "in notepad type X"
NOTEPAD_TYPE_DIRECT_RES = [
    re.compile(
        rf"^{_NP}{_NP_SUFFIX}{SEP_OPT}{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?){_END_IT}$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:in|into)\s+notepad\s*,?\s*{_WRITE}\s+{_TXT_SKIP}(?P<text>.+?)$",
        re.IGNORECASE,
    ),
]

# 3. Notepad: open + new tab only (no typing)
# Covers: "open notepad and create a new tab", "create a new tab in notepad"
NOTEPAD_TAB_ONLY_RES = [
    re.compile(
        rf"^{_NP}{_NP_SUFFIX}{SEP_OPT}{_TAB}(?:\s+in\s+notepad)?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^{_NP_BARE}{_NP_SUFFIX}{SEP_OPT}{_TAB}(?:\s+in\s+notepad)?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(?:in|on)\s+notepad\s*,?\s*{_TAB}\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^{_TAB}\s+(?:in|on)\s+notepad\s*$",
        re.IGNORECASE,
    ),
]

# 4. Open Notepad only
NOTEPAD_OPEN_ONLY_RES = [
    re.compile(rf"^{_NP}{_NP_SUFFIX}\s*$", re.IGNORECASE),
    re.compile(r"^notepad\s*$", re.IGNORECASE),
]

# 5. Generic App: new tab and type
GENERIC_APP_TAB_TYPE_RE = re.compile(
    r"^(?:open|launch|start)\s+(?:the\s+)?(?P<app>[a-zA-Z0-9 .+_-]{2,40}?)\s*(?:app|application)?"
    + SEP_OPT
    + r"(?:create|open|add)\s+(?:a\s+)?(?:new\s+)?tab"
    + SEP_OPT
    + r"(?:type|write|enter|input|put)\s+(?:(?:the|some|a)\s+)?(?:text\s+|words?\s+)?(?P<text>.+?)(?:\s+(?:in|into|on)\s+it)?$",
    re.IGNORECASE,
)

# Microsoft Store is a local Windows app. Handle the common open-and-search
# request deterministically so it does not get mistaken for a web search or
# spend several model turns discovering the search box.
STORE_SEARCH_RE = re.compile(
    r"^(?:"
    r"(?:open|launch|start)\s+(?:the\s+)?microsoft\s+store(?:\s+(?:app|application))?"
    r"\s*(?:(?:and\s+then|and|then|,)\s*)?(?:search(?:\s+for)?|find)\s+(?P<query_after_store>.+)"
    r"|(?:search(?:\s+for)?|find)\s+(?P<query_before_store>.+?)"
    r"\s+(?:in|on|from)\s+(?:the\s+)?microsoft\s+store(?:\s+(?:app|application))?"
    r")$",
    re.IGNORECASE,
)
STORE_INSTALL_SUFFIX_RE = re.compile(
    r"\s+(?:(?:and|then)\s+)?(?:download|install|get)\s+(?:it|this|that|the\s+(?:app|application|game))\s*$",
    re.IGNORECASE,
)
STORE_INSTALL_CHAIN_RE = re.compile(
    r"\b(?:and|then)\s+(?:please\s+)?(?:the\s+)?(?:download|install|get)\b",
    re.IGNORECASE,
)
STORE_SEARCH_UI_SUFFIX_RE = re.compile(
    r"\s+in\s+(?:the\s+)?search\s+(?:bar|box|field)\s*$",
    re.IGNORECASE,
)


def is_microsoft_store_install_request(query: str) -> bool:
    """True when a Store search request also asks to install/download the item."""
    if not query:
        return False
    normalized = query.strip().rstrip("?.!,;:")
    has_store = re.search(r"\bmicrosoft\s+store\b", normalized, re.IGNORECASE)
    has_search = re.search(r"\b(?:search(?:\s+for)?|find)\b", normalized, re.IGNORECASE)
    return bool(
        has_store
        and has_search
        and (STORE_INSTALL_SUFFIX_RE.search(normalized) or STORE_INSTALL_CHAIN_RE.search(normalized))
    )


def extract_microsoft_store_install_search_query(query: str) -> str | None:
    """Extract the item name from a Store search-and-install instruction."""
    if not is_microsoft_store_install_request(query):
        return None

    normalized = query.strip().rstrip("?.!,;:")
    action = STORE_INSTALL_CHAIN_RE.search(normalized)
    if action:
        search_instruction = normalized[: action.start()].rstrip(" ,;:")
    else:
        search_instruction = STORE_INSTALL_SUFFIX_RE.sub("", normalized).rstrip(" ,;:")

    match = STORE_SEARCH_RE.match(search_instruction)
    if not match:
        return None
    item = match.group("query_after_store") or match.group("query_before_store") or ""
    item = STORE_SEARCH_UI_SUFFIX_RE.sub("", item.strip())
    return item.strip().strip("'\"") or None


def resolve_windows_use_request(query: str) -> dict[str, Any] | None:
    """
    Fast (<1ms) query matcher to extract Windows compound desktop tasks
    without requiring LLM round-trips.
    """
    if not query or not query.strip():
        return None
    q = query.strip().rstrip("?.!,;:")

    store_match = STORE_SEARCH_RE.match(q)
    if store_match:
        # Search-only flow is deterministic and fast. A search followed by an
        # install is a multi-step visual task; let Laya route the full request
        # to the CUA agent instead of swallowing the suffix into the query.
        if is_microsoft_store_install_request(q):
            return None
        search_query = store_match.group("query_after_store") or store_match.group("query_before_store")
        return {
            "action": "microsoft_store_search",
            "app": "store",
            "query": search_query.strip().strip("'\""),
            "raw_query": query,
        }

    # These are legacy UI recipes, not dedicated API capabilities. Respect
    # the selected desktop engine across every caller, including preflight.
    # The dedicated Store search above retains its existing fast path.
    from .vercel_engine import desktop_enabled
    if desktop_enabled():
        return None

    # 1. Notepad: new tab and type
    for r in NOTEPAD_TAB_TYPE_RES:
        m = r.match(q)
        if m:
            text = m.group("text").strip().strip("'\"")
            return {
                "action": "notepad_new_tab_and_type",
                "app": "notepad",
                "text": text,
                "raw_query": query,
            }

    # 2. Notepad: open and type directly
    for r in NOTEPAD_TYPE_DIRECT_RES:
        m = r.match(q)
        if m:
            text = m.group("text").strip().strip("'\"")
            return {
                "action": "notepad_type",
                "app": "notepad",
                "text": text,
                "raw_query": query,
            }

    # 3. Notepad: new tab only
    for r in NOTEPAD_TAB_ONLY_RES:
        m = r.match(q)
        if m:
            return {
                "action": "notepad_new_tab",
                "app": "notepad",
                "text": "",
                "raw_query": query,
            }

    # 4. Notepad: open only
    for r in NOTEPAD_OPEN_ONLY_RES:
        m = r.match(q)
        if m:
            return {
                "action": "notepad_open",
                "app": "notepad",
                "text": "",
                "raw_query": query,
            }

    # 5. Generic app: new tab and type
    m5 = GENERIC_APP_TAB_TYPE_RE.match(q)
    if m5:
        app = m5.group("app").strip().lower()
        text = m5.group("text").strip().strip("'\"")
        return {
            "action": "app_new_tab_and_type",
            "app": app,
            "text": text,
            "raw_query": query,
        }

    return None


def execute_notepad_new_tab_and_type(text: str = "", new_tab: bool = True) -> dict[str, Any]:
    """
    Sub-second execution using native Windows-Use UIA:
    1. Ensures Notepad is open and brought to the foreground.
    2. Clicks the '+' New Tab button or presses Ctrl+N/Ctrl+T if requested.
    3. Finds the active text editor control (DocumentControl or EditControl).
    4. Focuses and types text directly with zero unnecessary waits.
    """
    t0 = time.perf_counter()
    import win32gui
    import windows_use.uia as uia
    from windows_use.agent.desktop.utils import escape_text_for_sendkeys

    # 1. Ensure Notepad is running and in foreground
    notepad_win = uia.WindowControl(RegexName=r"(?i).*notepad.*")
    if not notepad_win.Exists(maxSearchSeconds=0.2):
        subprocess.Popen(["notepad.exe"])
        notepad_win.Exists(maxSearchSeconds=2.5)

    if not notepad_win.Exists(maxSearchSeconds=0.8):
        return {
            "success": False,
            "message": "Could not find or launch Notepad.",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }

    try:
        win32gui.SetForegroundWindow(notepad_win.NativeWindowHandle)
    except Exception:
        notepad_win.SetActive()

    # 2. Open new tab if requested: Look for '+' / 'New tab' button via UIA, fallback to Ctrl+T
    if new_tab:
        new_tab_btn = notepad_win.ButtonControl(RegexName=r"(?i).*(new tab|add tab|\+).*")
        if new_tab_btn.Exists(maxSearchSeconds=0.3):
            try:
                pattern = new_tab_btn.GetInvokePattern()
                if pattern:
                    pattern.Invoke()
                else:
                    new_tab_btn.Click(simulateMove=False, waitTime=0.05)
            except Exception:
                new_tab_btn.Click(simulateMove=False, waitTime=0.05)
        else:
            uia.SendKeys("{Ctrl}t", waitTime=0.05)

    # 3. Locate DocumentControl or EditControl
    doc = notepad_win.DocumentControl()
    if not doc.Exists(maxSearchSeconds=0.3):
        doc = notepad_win.EditControl()

    if doc.Exists(maxSearchSeconds=0.5):
        try:
            doc.SetFocus()
        except Exception:
            pass
        rect = doc.BoundingRectangle
        center = (rect.left + rect.width() // 2, rect.top + rect.height() // 2)
        if text:
            uia.Click(center[0], center[1], waitTime=0.05)
            # Send Escape first to dismiss any active Alt/AccessKey ribbon hints before typing
            uia.SendKeys("{Escape}" + escape_text_for_sendkeys(text), interval=0.005, waitTime=0.05)
    else:
        # Fallback to center of Notepad window
        rect = notepad_win.BoundingRectangle
        center = (rect.left + rect.width() // 2, rect.top + rect.height() // 2)
        if text:
            uia.Click(center[0], center[1], waitTime=0.05)
            uia.SendKeys("{Escape}" + escape_text_for_sendkeys(text), interval=0.005, waitTime=0.05)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if new_tab and text:
        msg = f"Opened Notepad, created a new tab, and typed '{text}'."
    elif new_tab:
        msg = "Opened Notepad and created a new tab."
    elif text:
        msg = f"Opened Notepad and typed '{text}'."
    else:
        msg = "Opened Notepad."

    LOGGER.info("%s (completed in %d ms)", msg, elapsed_ms)

    return {
        "success": True,
        "message": msg,
        "app": "notepad",
        "text": text,
        "elapsed_ms": elapsed_ms,
    }


def execute_notepad_open() -> dict[str, Any]:
    """Open Notepad and bring it to the foreground."""
    t0 = time.perf_counter()
    import win32gui
    import windows_use.uia as uia

    notepad_win = uia.WindowControl(RegexName=r"(?i).*notepad.*")
    if not notepad_win.Exists(maxSearchSeconds=0.2):
        subprocess.Popen(["notepad.exe"])
        notepad_win.Exists(maxSearchSeconds=2.5)

    if notepad_win.Exists(maxSearchSeconds=0.5):
        try:
            win32gui.SetForegroundWindow(notepad_win.NativeWindowHandle)
        except Exception:
            notepad_win.SetActive()

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    LOGGER.info("Opened Notepad. (completed in %d ms)", elapsed_ms)
    return {
        "success": True,
        "message": "Opened Notepad.",
        "app": "notepad",
        "text": "",
        "elapsed_ms": elapsed_ms,
    }


def handle_windows_use_request(params: dict[str, Any]) -> dict[str, Any]:
    """Main execution dispatcher for resolved Windows-Use requests."""
    action = params.get("action")

    if action == "microsoft_store_search":
        return execute_microsoft_store_search(str(params.get("query") or "").strip())

    if action == "notepad_new_tab_and_type":
        return execute_notepad_new_tab_and_type(params.get("text", ""), new_tab=True)

    if action == "notepad_new_tab":
        return execute_notepad_new_tab_and_type("", new_tab=True)

    if action == "notepad_type":
        return execute_notepad_new_tab_and_type(params.get("text", ""), new_tab=False)

    if action == "notepad_open":
        return execute_notepad_open()

    if action == "app_new_tab_and_type":
        app = params.get("app", "")
        if "notepad" in app:
            return execute_notepad_new_tab_and_type(params.get("text", ""), new_tab=True)

    # Generic agent fallback
    query = params.get("raw_query") or params.get("query")
    if query:
        return run_windows_use_agent_task(query)

    return {
        "success": False,
        "message": f"Unsupported Windows-Use action: {action}",
    }


def execute_microsoft_store_search(query: str) -> dict[str, Any]:
    """Search Microsoft Store through visible GUI actions and verify the result."""
    started = time.perf_counter()
    if not query:
        return {"success": False, "message": "I need a search term for Microsoft Store."}

    from computer_use.tools import open_app_tool

    launch = open_app_tool("store")
    if not launch.success:
        return {"success": False, "message": launch.message}

    from computer_use.actuator import _cua_backend, click_element, type_text
    from computer_use.cursor_bridge import agent_cursor_events, emit_cursor_protocol_event

    backend = _cua_backend()
    if backend is None:
        return {
            "success": False,
            "message": "Microsoft Store opened, but Blinky's cursor input backend is unavailable.",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    _store_window, focus_error = _focus_store_foreground(backend)
    if focus_error:
        return {
            "success": False,
            "message": f"Microsoft Store opened, but Blinky could not bring its window to the foreground: {focus_error}",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    # Store can take a moment to create its window after the launcher returns.
    # Prefer a semantic UIA click. Some Store builds expose an empty UIA tree,
    # so fall back to the stable center of the visible Store search bar using
    # the Store window's physical screen bounds. This keeps the click away from
    # the title-bar controls and uses the same Blinky cursor/backend path.
    deadline = time.monotonic() + 3.5
    with agent_cursor_events(emit_cursor_protocol_event):
        click_result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            candidate = click_element(name="Search", app_id="store")
            if candidate.get("ok"):
                click_result = candidate
                break
            time.sleep(0.3)

        if click_result is None:
            store_window = _find_visible_store_window(backend)
            if store_window is None:
                return {
                    "success": False,
                    "message": "Microsoft Store opened, but Blinky could not find its visible window to click Search.",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }

            search_x = int(store_window.x + store_window.width / 2)
            search_y = int(store_window.y + min(24, max(18, round(store_window.height * 0.015))))
            click_result = click_element(
                x=search_x,
                y=search_y,
                name="Microsoft Store search field",
                app_id="store",
            )
            if not click_result.get("ok"):
                return {
                    "success": False,
                    "message": f"Microsoft Store is open, but Blinky could not click its visible Search field: {click_result.get('message', 'click failed')}.",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }

        typed: dict[str, Any]
        element_token = str(click_result.get("element_token") or "").strip()
        target_pid = click_result.get("pid")
        element_backend = _cua_backend() if element_token and target_pid is not None else None
        value_result = None
        if element_backend is not None:
            try:
                value_result = element_backend.set_value(
                    element_token=element_token,
                    pid=int(target_pid),
                    value=query,
                )
            except Exception as exc:
                LOGGER.debug("Store Search UIA value set failed; using targeted typing: %s", exc)

        if value_result is not None and value_result.ok:
            typed = {"ok": True, "message": value_result.message}
        else:
            # This still targets the Store window explicitly (scope=window),
            # rather than sending keys to whichever overlay happens to be frontmost.
            typed = type_text(query, target_app="store")
        if not typed.get("ok"):
            # Store is a CoreWindow/UWP surface. cua-driver's background text
            # path can fail even after a successful visible click. Keep the
            # Blinky cursor for the click, then focus the same Store HWND and
            # use Windows foreground keyboard input for text.
            typed = _send_store_foreground_text(backend, query)
        if not typed.get("ok"):
            return {
                "success": False,
                "message": f"Focused Microsoft Store Search, but could not enter the query: {typed.get('message', 'input failed')}.",
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
        # CUA can report a targeted key as dispatched even when the Store
        # CoreWindow ignores it. Send Enter through the focused foreground
        # Store window, then verify the rendered page before reporting success.
        submitted = _send_store_foreground_key(backend, "{ENTER}")
        if not submitted.get("ok"):
            return {
                "success": False,
                "message": f"Entered '{query}' in Microsoft Store, but could not submit the search.",
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }

    # Use local OCR as the completion gate. The vision model has called the
    # Store home screen a successful search, so its response is not enough.
    time.sleep(0.9)
    screenshot_path = _capture_store_search_screenshot(backend)
    verification = _verify_store_search_with_ocr(screenshot_path, query)

    if not verification.get("verified"):
        # Store can leave focus in the text box after Enter. Click its visible
        # magnifier button with Blinky's cursor as a GUI fallback; never click
        # a recommendation such as the Minecraft Launcher tile.
        store_window = _find_visible_store_window(backend)
        if store_window is not None:
            search_button_x = int(store_window.x + store_window.width * 0.735)
            search_button_y = int(store_window.y + min(36, max(24, round(store_window.height * 0.025))))
            with agent_cursor_events(emit_cursor_protocol_event):
                clicked_search = click_element(
                    x=search_button_x,
                    y=search_button_y,
                    name="Microsoft Store submit search button",
                    app_id="store",
                )
            if clicked_search.get("ok"):
                time.sleep(1.0)
                screenshot_path = _capture_store_search_screenshot(backend)
                verification = _verify_store_search_with_ocr(screenshot_path, query)

    if not verification.get("verified"):
        observation = str(verification.get("observation") or "Store results were not confirmed")
        return {
            "success": False,
            "message": f"Blinky clicked Search, typed '{query}', and pressed Enter, but could not confirm the Store results: {observation}.",
            "app": "store",
            "query": query,
            "method": "gui_click_type_verify",
            "verification": verification,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "success": True,
        "message": f"Searched Microsoft Store for '{query}'.",
        "app": "store",
        "query": query,
        "method": "gui_click_type_verify",
        "verification": verification,
        "elapsed_ms": elapsed_ms,
    }


def execute_microsoft_store_install_from_results(query: str) -> dict[str, Any]:
    """Use Store UIA to open the exact result and start its install if exposed.

    Vision is deliberately left as the caller's fallback. We only click a
    unique, exact UIA match for the app and a unique standard install button.
    """
    backend = _cua_backend()
    if backend is None:
        return {"success": False, "fallback_required": True, "message": "Store UI Automation is unavailable."}

    window, focus_error = _focus_store_foreground(backend)
    if focus_error or window is None:
        return {
            "success": False,
            "fallback_required": True,
            "message": focus_error or "Microsoft Store could not be focused.",
        }

    elements = backend.get_window_elements(window.window_id, pid=window.pid)
    if not elements or getattr(backend, "last_snapshot_degraded", None):
        return {
            "success": False,
            "fallback_required": True,
            "message": "Microsoft Store did not expose a usable UI Automation tree.",
        }

    item_key = _normalize_store_accessible_name(query)
    clickable_roles = {"button", "listitem", "hyperlink", "custom"}
    exact_items = [
        element for element in elements
        if _normalize_store_accessible_name(element.text) == item_key
        and str(element.role or "").casefold() in clickable_roles
        and element.extra.get("enabled") is not False
    ]
    if len(exact_items) != 1:
        return {
            "success": False,
            "fallback_required": True,
            "message": f"Store UI Automation did not expose one unambiguous {query!r} result.",
        }

    clicked = _click_store_uia_element(backend, exact_items[0], query)
    if not clicked:
        return {
            "success": False,
            "fallback_required": True,
            "message": f"Could not open the exact {query!r} Store result through UI Automation.",
        }

    # Let the product page load, then inspect the fresh Store tree. Requiring a
    # single standard action name avoids clicking unrelated cards or chrome.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        time.sleep(0.35)
        window = _find_visible_store_window(backend)
        if window is None:
            continue
        elements = backend.get_window_elements(window.window_id, pid=window.pid)
        if not elements or getattr(backend, "last_snapshot_degraded", None):
            continue

        item_still_visible = any(
            item_key in _normalize_store_accessible_name(element.text)
            for element in elements
        )
        if not item_still_visible:
            continue

        already_active = [
            element for element in elements
            if str(element.role or "").casefold() == "button"
            and re.search(r"\b(?:downloading|installing|pending|queued|installed|open)\b", element.text, re.IGNORECASE)
        ]
        if already_active:
            return {
                "success": True,
                "fallback_required": False,
                "message": f"Microsoft Store shows {query} as {already_active[0].text.strip()}.",
                "method": "store_uia",
            }

        install_controls = [
            element for element in elements
            if str(element.role or "").casefold() == "button"
            and re.fullmatch(r"\s*(?:get|install|download)(?:\s+(?:now|free))?\s*", element.text, re.IGNORECASE)
            and element.extra.get("enabled") is not False
        ]
        if len(install_controls) == 1:
            if not _click_store_uia_element(backend, install_controls[0], install_controls[0].text.strip()):
                return {
                    "success": False,
                    "fallback_required": True,
                    "message": "Store exposed its install button, but UI Automation could not click it.",
                }

            verify_deadline = time.monotonic() + 3.0
            while time.monotonic() < verify_deadline:
                time.sleep(0.35)
                current_window = _find_visible_store_window(backend)
                if current_window is None:
                    continue
                current = backend.get_window_elements(current_window.window_id, pid=current_window.pid)
                state = next((
                    element.text.strip() for element in current
                    if str(element.role or "").casefold() == "button"
                    and re.search(r"\b(?:downloading|installing|pending|queued|installed|open)\b", element.text, re.IGNORECASE)
                ), None)
                if state:
                    return {
                        "success": True,
                        "fallback_required": False,
                        "message": f"Clicked {install_controls[0].text.strip()} for {query}; Microsoft Store now shows {state}.",
                        "method": "store_uia",
                    }

            return {
                "success": False,
                "fallback_required": True,
                "message": "Clicked the Store install control, but UI Automation could not confirm the result.",
            }

    return {
        "success": False,
        "fallback_required": True,
        "message": "Opened the Store result, but its install control was not exposed clearly by UI Automation.",
    }


def _normalize_store_accessible_name(value: str) -> str:
    return " ".join(re.sub(r"[^\w ]+", " ", str(value or "").casefold()).split())


def _click_store_uia_element(backend: Any, element: Any, label: str) -> bool:
    """Click a snapshot-bound Store UIA element with Blinky's cursor animation."""
    extra = element.extra or {}
    window_id = extra.get("window_id")
    pid = extra.get("pid")
    index = extra.get("element_index")
    token = str(extra.get("element_token") or "").strip() or None
    if window_id is None or pid is None or (index is None and token is None):
        return False

    from computer_use.cursor_bridge import run_with_agent_cursor

    x, y = element.center()
    try:
        result = run_with_agent_cursor(
            lambda: backend.click_element(
                element_index=int(index) if index is not None else None,
                element_token=token,
                window_id=str(window_id),
                pid=int(pid),
                snapshot_id=extra.get("snapshot_id"),
            ),
            x=x,
            y=y,
            label=label,
        )
        return bool(result and result.ok)
    except Exception as exc:
        LOGGER.warning("Store UIA click failed for %r: %s", label, exc)
        return False


def _verify_store_search_with_ocr(screenshot_path: str | None, query: str) -> dict[str, Any]:
    if not screenshot_path:
        return {"verified": False, "observation": "No screenshot available for local OCR", "confidence": 0.0}

    try:
        from pathlib import Path

        from ocr import extract_visible_text

        items = extract_visible_text(Path(screenshot_path))
        visible_text = " ".join(str(item.get("text", "")) for item in items).casefold()
        normalized_query = " ".join(query.casefold().split())
        occurrences = visible_text.count(normalized_query)
        has_results_heading = bool(
            re.search(r"\bsearch\s+results?\b|\bresults?\s+for\b", visible_text)
        )
        if (
            normalized_query
            and occurrences >= 2
            and has_results_heading
            and "trending games" not in visible_text
        ):
            return {
                "verified": True,
                "observation": "Local OCR confirmed the Store search results heading and query",
                "confidence": 0.8,
                "verification_method": "local_ocr",
            }
        return {
            "verified": False,
            "observation": (
                f"Store results not visible (query occurrences: {occurrences}, "
                f"results heading: {has_results_heading})"
            ),
            "confidence": 0.0,
            "verification_method": "local_ocr",
        }
    except Exception as exc:
        LOGGER.warning("Local OCR could not verify Microsoft Store results: %s", exc)
        return {
            "verified": False,
            "observation": f"Local OCR unavailable: {exc}",
            "confidence": 0.0,
            "verification_method": "local_ocr",
        }


def _capture_store_search_screenshot(backend: Any) -> str | None:
    """Capture only the Store window so unrelated desktop text cannot pass OCR."""
    store_window = _find_visible_store_window(backend)
    if store_window is None:
        return None

    try:
        screenshot = backend._capture_window(store_window)
        return str(screenshot.path)
    except Exception as exc:
        LOGGER.warning("Could not capture Microsoft Store window directly: %s", exc)

    _window, focus_error = _focus_store_foreground(backend)
    if focus_error:
        LOGGER.warning("Cannot use desktop screenshot for Store verification: %s", focus_error)
        return None

    try:
        from computer_use.tools import capture_screenshot

        return capture_screenshot()
    except Exception as exc:
        LOGGER.warning("Could not capture foreground Microsoft Store screen: %s", exc)
        return None


def _find_visible_store_window(backend: Any) -> Any | None:
    candidates = [
        window
        for window in _find_store_windows(backend)
        if window.supported and window.width >= 800 and window.height >= 500
    ]
    return max(candidates, key=lambda window: window.width * window.height, default=None)


def _find_store_windows(backend: Any) -> list[Any]:
    try:
        windows = backend.list_windows()
    except Exception as exc:
        LOGGER.warning("Could not inspect Store window bounds: %s", exc)
        return []

    candidates = [
        window
        for window in windows
        if (
            "store" in (window.title or "").lower()
            or "store" in (window.process or "").lower()
        )
    ]
    return sorted(
        candidates,
        key=lambda window: (
            bool(window.supported and window.width >= 800 and window.height >= 500),
            window.width * window.height,
        ),
        reverse=True,
    )


def _focus_store_foreground(backend: Any) -> tuple[Any | None, str | None]:
    candidates = _find_store_windows(backend)
    if not candidates:
        return None, "No Microsoft Store window is available for keyboard input."

    try:
        import win32gui
        import win32process

        for window in candidates:
            try:
                hwnd = int(window.window_id)
            except (TypeError, ValueError):
                continue
            if not win32gui.IsWindow(hwnd):
                continue

            # Store is hosted by ApplicationFrameHost. Its frame can linger as
            # an off-screen 219x39 window after the Store is minimized; restore
            # the native HWND before sending mouse or keyboard input.
            win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
            try:
                focus_result = backend.focus_window(window.window_id, pid=window.pid)
                if not focus_result.ok:
                    LOGGER.debug("CUA could not bring Store to the foreground: %s", focus_result.message)
            except Exception as exc:
                LOGGER.debug("CUA foreground activation failed for Store: %s", exc)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.12)

            if not win32gui.IsWindowVisible(hwnd):
                continue
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right - left < 800 or bottom - top < 500:
                continue
            foreground = win32gui.GetForegroundWindow()
            _, foreground_pid = win32process.GetWindowThreadProcessId(foreground)
            _, target_pid = win32process.GetWindowThreadProcessId(hwnd)
            if foreground != hwnd and foreground_pid != target_pid:
                continue

            invalidate = getattr(backend, "_invalidate_windows_cache", None)
            if callable(invalidate):
                invalidate()
            refreshed = _find_visible_store_window(backend)
            if refreshed is None:
                continue
            return refreshed, None
    except Exception as exc:
        return None, f"Could not focus Microsoft Store for keyboard input: {exc}"

    return None, "Microsoft Store could not be restored as a visible foreground window."


def _send_store_foreground_text(backend: Any, text: str) -> dict[str, Any]:
    # The caller has already focused Store and clicked its search field. Do not
    # bring the top-level HWND forward here: that can move focus off the field.
    _window, error = _get_store_foreground_window(backend)
    if error:
        return {"ok": False, "message": error}
    try:
        from pywinauto.keyboard import send_keys
        from windows_use.agent.desktop.utils import escape_text_for_sendkeys

        # The click above gives focus to the visible Store field. Replace any
        # previous query, then type literal text through Windows foreground input.
        send_keys("^a")
        send_keys(escape_text_for_sendkeys(text), with_spaces=True, pause=0.005)
        return {"ok": True, "message": "Typed into the foreground Microsoft Store window."}
    except Exception as exc:
        LOGGER.warning("Foreground Store text input failed: %s", exc)
        return {"ok": False, "message": str(exc)}


def _send_store_foreground_key(backend: Any, key: str) -> dict[str, Any]:
    # Preserve the focused child search control. Refocusing the top-level Store
    # HWND immediately before Enter can steal keyboard focus from that control.
    _window, error = _get_store_foreground_window(backend)
    if error:
        return {"ok": False, "message": error}
    try:
        from pywinauto.keyboard import send_keys

        send_keys(key)
        return {"ok": True, "message": "Pressed Enter in the foreground Microsoft Store window."}
    except Exception as exc:
        LOGGER.warning("Foreground Store key input failed: %s", exc)
        return {"ok": False, "message": str(exc)}


def _get_store_foreground_window(backend: Any) -> tuple[Any | None, str | None]:
    window = _find_visible_store_window(backend)
    if window is None:
        return None, "No visible Microsoft Store window is available for keyboard input."
    try:
        import win32gui
        import win32process

        foreground = win32gui.GetForegroundWindow()
        _, foreground_pid = win32process.GetWindowThreadProcessId(foreground)
        if foreground_pid != window.pid:
            return None, "Microsoft Store is not the foreground window; search-field focus was preserved."
    except Exception as exc:
        return None, f"Could not confirm Microsoft Store is foreground: {exc}"
    return window, None


def run_windows_use_agent_task(task: str) -> dict[str, Any]:
    """
    Autonomous multi-step Windows-Use Agent task loop backed by Groq or Gemini.
    """
    t0 = time.perf_counter()
    from windows_use import Agent

    llm = None
    # 1. Try Groq (fastest inference: ~300ms)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from windows_use.providers.groq import ChatGroq
            llm = ChatGroq(model="qwen/qwen3.8-27b", api_key=groq_key)
        except Exception as exc:
            LOGGER.debug("Could not initialize Groq for Windows-Use: %s", exc)

    # 2. Try Gemini
    if llm is None:
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            try:
                from windows_use.providers.google import ChatGoogle
                llm = ChatGoogle(model="gemini-3.8-flash", api_key=gemini_key)
            except Exception as exc:
                LOGGER.debug("Could not initialize Gemini for Windows-Use: %s", exc)

    if llm is None:
        return {
            "success": False,
            "message": "No valid LLM provider available for Windows-Use Agent.",
        }

    try:
        agent = Agent(llm=llm, max_steps=10, log_to_console=False)
        result = agent.invoke(task=task)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "success": True,
            "message": result.content or "Task completed.",
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        LOGGER.exception("Windows-Use agent task failed")
        return {
            "success": False,
            "message": f"Windows-Use task failed: {exc}",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }
