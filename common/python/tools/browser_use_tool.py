#!/usr/bin/env python3
"""
Browser-Use Autonomous Web Agent Tool for Blinky.

Enables Blinky to autonomously navigate the web, inspect interactive DOM elements,
click buttons, fill forms, extract data, and perform multi-step web automation
using the `browser-use` library and Microsoft Edge / Chromium.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

LOGGER = logging.getLogger("blinky.tools.browser_use")

DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODEL = "gemini-3.1-flash-lite"


def get_browser_use_llm():
    """Resolve and instantiate primary and fallback LLMs for browser-use."""
    from browser_use import ChatGoogle, ChatOpenAI, ChatGroq

    # 1. Primary: Google Gemini
    gemini_key = (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    if not gemini_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            gemini_key = (
                os.getenv("GEMINI_API_KEY", "").strip()
                or os.getenv("GOOGLE_API_KEY", "").strip()
            )
        except Exception:
            pass

    if gemini_key:
        primary = ChatGoogle(model=DEFAULT_MODEL, api_key=gemini_key)
        fallback = ChatGoogle(model=FALLBACK_MODEL, api_key=gemini_key)
        return primary, fallback

    # 2. Secondary: OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        primary = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key)
        return primary, None

    # 3. Tertiary: Groq
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        primary = ChatGroq(model="llama-3.3-70b-versatile", api_key=groq_key)
        return primary, None

    raise RuntimeError("No LLM API key found for browser-use. Please set GEMINI_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY.")


def check_cdp_available(host: str = "127.0.0.1", port: int = 9222, timeout: float = 0.2) -> bool:
    """Check if Chrome DevTools Protocol remote debugging port is open."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_existing_browser_endpoint() -> str | None:
    """Discover the user's running Chromium browser session (Edge, Chrome, Brave)
    without launching or copying profiles, reading DevToolsActivePort from %LOCALAPPDATA%
    or checking fixed port 9222."""
    import socket
    from pathlib import Path

    # 1. Environment variable override
    configured = (
        os.getenv("BLINKY_BROWSER_CDP_URL")
        or os.getenv("DIGITALSOUL_BROWSER_CDP_URL")
        or os.getenv("DIGITALSOUL_EDGE_CDP_URL")
    )
    if configured:
        return configured.strip()

    # 2. Check standard fixed port 9222
    if check_cdp_available("127.0.0.1", 9222):
        return "http://localhost:9222"

    # 3. Read DevToolsActivePort from browser user profile folders (Edge, Chrome, Brave)
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    candidates = [
        ("Microsoft/Edge/User Data", "Edge"),
        ("Google/Chrome/User Data", "Chrome"),
        ("BraveSoftware/Brave-Browser/User Data", "Brave"),
    ]
    for folder, label in candidates:
        port_file = local / folder / "DevToolsActivePort"
        if port_file.is_file():
            try:
                lines = port_file.read_text(encoding="utf-8").strip().splitlines()
                if len(lines) >= 2 and lines[0].isdigit() and lines[1].startswith("/devtools/browser/"):
                    port = int(lines[0])
                    path = lines[1].strip()
                    # Verify port is currently alive
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.3)
                        if s.connect_ex(("127.0.0.1", port)) == 0:
                            ws_url = f"ws://127.0.0.1:{port}{path}"
                            LOGGER.info("Connected to existing %s session via DevToolsActivePort: %s", label, ws_url)
                            return ws_url
            except Exception as exc:
                LOGGER.debug("Error checking DevToolsActivePort for %s: %s", label, exc)
    return None


async def run_browser_task(
    task: str,
    max_steps: int = 15,
    headless: bool | None = None,
    channel: str | None = None,
    cdp_url: str | None = None,
    cursor_sink=None,
) -> dict[str, Any]:
    """Execute an autonomous web browsing task using browser-use and Microsoft Edge/Chrome."""
    engine = os.getenv("BLINKY_BROWSER_ENGINE", "agent-browser").strip().lower()
    if engine == "agent-browser":
        from computer_use.vercel_engine import run_task
        from computer_use.browser_context import browser_continuation
        continuation = browser_continuation(task)
        history = continuation.get("history", []) if continuation else None
        if continuation:
            task = continuation["task"]
        endpoint = cdp_url or get_existing_browser_endpoint()
        return await asyncio.to_thread(run_task, task, "agent-browser", max_steps, endpoint, cursor_sink=cursor_sink,
                                       previous_actions=history)
    if engine != "browser_use":
        raise ValueError("BLINKY_BROWSER_ENGINE must be agent-browser or browser_use.")

    from browser_use import Agent, Browser

    if headless is None:
        headless_val = os.getenv("BLINKY_BROWSER_HEADLESS", "false").strip().lower()
        headless = headless_val in {"1", "true", "yes", "on"}

    if channel is None:
        channel = os.getenv("BLINKY_BROWSER_CHANNEL", "msedge").strip() or "msedge"

    if cdp_url is None:
        cdp_url = get_existing_browser_endpoint()

    llm, fallback_llm = get_browser_use_llm()
    if cdp_url:
        LOGGER.info("Connecting browser-use to existing browser via CDP: %s for task: '%s'", cdp_url, task)
        browser = Browser(cdp_url=cdp_url, is_local=True, use_cloud=False, enable_default_extensions=False, auto_download_pdfs=False)
    else:
        requires_existing = any(w in task.lower() for w in ["existing", "currently opened", "already opened", "my browser", "open browser", "current tab", "current browser"])
        if requires_existing:
            raise RuntimeError(
                "Could not connect to your existing browser because remote debugging is not active. "
                "To automate your currently open window without restarting, prompt Blinky: "
                "'Look at my screen and complete the assessment in the active window' (using Desktop Automation)."
            )
        LOGGER.info("Starting fresh browser-use agent for task: '%s' (channel=%s, headless=%s)", task, channel, headless)
        browser = Browser(channel=channel, headless=headless)
    agent_kwargs: dict[str, Any] = {
        "task": task,
        "llm": llm,
        "browser": browser,
        "use_vision": True,
        "use_judge": False,
    }
    if fallback_llm is not None:
        agent_kwargs["fallback_llm"] = fallback_llm

    agent = Agent(**agent_kwargs)

    history = await agent.run(max_steps=max_steps)
    final_res = history.final_result() or "Browser task completed."
    errors = history.errors()

    return {
        "success": True,
        "action": "browser_use",
        "task": task,
        "result": final_res,
        "steps": len(history.action_names()),
        "errors": [str(e) for e in errors] if errors else [],
    }


BROWSER_USE_PATTERNS = (
    r"\bagent[- ]browser\b",
    r"\b(?:read|click|fill|type|scroll|inspect|summarize|check|select|press|complete)\b.*\b(?:current\s+tab|active\s+tab|current\s+browser|my\s+browser|existing\s+browser)\b",
    # 1. Direct URL navigation with any follow-up instruction (e.g. "go to https://... and tell me...", "open https://... to check...")
    r"\b(?:go\s+to|navigate\s+to|visit|browse|open\s+website|open\s+url|open)\s+(https?://[^\s]+|\S+\.(?:com|org|io|net|edu|gov|dev|ai|app|co))\b(?:\s+(?:and|to|then)\s+.+|\s*$)",
    # 2. General URL with information/action request (e.g. "tell me / extract / get / check / read ... from/on/at <url>")
    r"\b(?:tell\s+me|find|extract|scrape|get|check|read|see|show|look\s+up|summarize)\b.+?\b(?:on|in|at|from|of)\s+(https?://[^\s]+|\S+\.(?:com|org|io|net|edu|gov|dev|ai|app|co))\b",
    # 3. Explicit web/browser agent keywords
    r"\b(?:automate\s+(?:the\s+)?(?:browser|website|web)|use\s+browser|agent\s+in\s+browser|browser\s+agent|browser-use|browser\s+use|web\s+agent)\b",
    # 4. Actions on webpage elements (click/press/fill/sign in/submit on <url>)
    r"\b(?:click|press|fill|sign\s+in|log\s+in|submit|type)\b.+?\b(?:on|in|at|to)\s+(?:https?://|\w+\.(?:com|org|io|net|dev|ai|app|co))\b",
    # 5. Extract/scrape/pull/read content from URL
    r"\b(?:extract|scrape|pull|read|fetch|get)\s+(?:the\s+)?(?:data|table|prices|items|products|contributors|reviews|comments|heading|text|info|posts)\s+(?:from|on|at|of)\s+(https?://\S+|\S+\.(?:com|org|io|net|dev|ai|app|co))\b",
)


def resolve_browser_use_request(query: str) -> dict[str, Any] | None:
    """Parse query to detect if it requires autonomous browser-use agent execution."""
    if not query:
        return None

    q = query.strip()
    q_lower = q.lower()

    from computer_use.browser_context import browser_continuation
    if browser_continuation(q):
        return {"action": "browser_use", "task": q, "raw_prompt": q}

    from computer_use.dedicated_routes import resolve_dedicated_request
    if resolve_dedicated_request(q):
        return None
    if re.fullmatch(r"(?:please\s+)?(?:open|create|add|click)(?:\s+on)?\s+(?:(?:a|the)\s+)?new\s+(?:browser\s+)?tab(?:\s+(?:button|icon))?[.!?]*", q, re.I):
        return {"action": "browser_use", "task": q, "raw_prompt": q}

    # Short follow-ups omit the site name: preserve the destination of the
    # previous browser task rather than sending page controls through Windows UIA.
    from computer_use.browser_context import recent_browser_context
    followup = re.match(r"^(?:please\s+)?(?:highlight|point\s+to|locate|play|pause|resume|click|press|select|scroll|read|summarize|fill|type|write|ask|send|reply|submit|subscribe|unsubscribe)\b", q, re.I)
    named_app = re.search(r"\b(?:vscode|vs\s+code|visual\s+studio\s+code|notepad|spotify|vlc|file\s+explorer|microsoft\s+store)\b", q, re.I)
    if followup and not named_app and recent_browser_context():
        return {"action": "browser_use", "task": q, "raw_prompt": q}
    # Chat requests often say 'ask Gemini ...' without a browser keyword.
    # The quoted question is payload, not a separate local app instruction.
    chat_site = re.search(r"\b(?:gemini|chatgpt|chat\s+gpt|claude|copilot)\b", q, re.I)
    chat_action = re.match(r"^(?:(?:please|can you|could you)\s+)?(?:ask|tell|message|send|type|write|reply|open|visit|click|fill)\b", q, re.I)
    if chat_site and chat_action:
        return {"action": "browser_use", "task": q, "raw_prompt": q}
    if re.search(r"\b(?:youtube|you\s+tube)\b", q, re.I) and re.search(r"\b(?:play|pause|click|subscribe|read|scroll|select|find)\b", q, re.I):
        return {"action": "browser_use", "task": q, "raw_prompt": q}

    destination = re.match(r"^(?:(?:please|can you|could you)\s+)?(?:open|visit|browse|navigate to)\s+(?:the\s+)?(.+?)(?=\s+(?:and|then)\b|$)", q_lower)
    if destination:
        from computer_use.tools import WEB_DESTINATION_URLS
        if destination[1].strip().rstrip(".!?") in WEB_DESTINATION_URLS:
            return {"action": "browser_use", "task": q, "raw_prompt": q}

    if re.search(r"https?://|www\.", q, re.I):
        return {"action": "browser_use", "task": q, "raw_prompt": q}
    browser_context = re.search(r"\b(?:browser|website|webpage|current tab|active tab|chrome|edge|firefox|brave)\b", q_lower)
    site_context = re.search(r"\b(?:open|visit|browse|navigate to|on|from|at)\s+(?:the\s+)?(?:instagram|gmail|github|chatgpt)\b", q_lower)
    if re.search(r"\b(?:highlight|locate|point|open|visit|browse|navigate|click|read|fill|search|select|type|scroll)\b", q_lower) and (browser_context or site_context):
        return {"action": "browser_use", "task": q, "raw_prompt": q}

    # Skip simple single-cell Excel typing or simple spreadsheet requests
    if q_lower.startswith(("write", "type", "put", "enter")) and "cell" in q_lower:
        return None

    for pattern in BROWSER_USE_PATTERNS:
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            return {
                "action": "browser_use",
                "task": q,
                "raw_prompt": q,
            }

    # Explicit browser automation triggers
    if any(k in q_lower for k in ("browser-use", "browser use", "autonomous browser", "web agent")):
        return {
            "action": "browser_use",
            "task": q,
            "raw_prompt": q,
        }

    # If query contains explicit http/https URL and asks for web action or inspection
    if re.search(r"https?://", q, re.IGNORECASE):
        url_action_keywords = (
            "tell me", "first comment", "comment", "comments", "latest", "post", "posts",
            "video", "videos", "check", "find", "extract", "scrape", "get", "read", "see",
            "show", "heading", "title", "summarize", "page", "website", "who", "what"
        )
        if any(kw in q_lower for kw in url_action_keywords):
            return {
                "action": "browser_use",
                "task": q,
                "raw_prompt": q,
            }

    return None
