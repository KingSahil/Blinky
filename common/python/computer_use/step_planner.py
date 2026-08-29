"""
Procedural Step Planner for Blinky Agent Mode.

Generates structured markdown guides and atomic action sequences for multi-step tasks
using SearXNG search + Groq text model (ask_text_model).
Eliminates vision model token overhead and 429 rate limit hallucinations.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import threading
from concurrent.futures import Future
from typing import Any

from ai.client import ask_text_model
from utils.logging import get_logger

LOGGER = get_logger("blinky.computer_use.step_planner")

# Common built-in procedural templates for instant zero-latency offline fallbacks
_COMMON_PROCEDURAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "dark_mode": {
        "patterns": [r"dark\s*mode", r"dark\s*theme", r"switch\s*to\s*dark", r"enable\s*dark"],
        "msedge": {
            "markdown": "# Enable Dark Mode in Microsoft Edge\n\n1. Open Edge Settings\n2. Click Appearance\n3. Select 'Dark' theme",
            "steps": [
                {"step": 1, "target": "Appearance", "action": "click", "instruction": "Click 'Appearance' in Edge Settings."},
                {"step": 2, "target": "Dark", "action": "click", "instruction": "Select 'Dark' overall appearance theme in Edge."},
            ],
            "app_to_open": "edge://settings/appearance",
        },
        "chrome": {
            "markdown": "# Enable Dark Mode in Google Chrome\n\n1. Open Chrome Settings\n2. Click Appearance\n3. Select 'Dark' mode",
            "steps": [
                {"step": 1, "target": "Appearance", "action": "click", "instruction": "Click 'Appearance' in Chrome Settings."},
                {"step": 2, "target": "Dark", "action": "click", "instruction": "Select 'Dark' theme in Chrome."},
            ],
            "app_to_open": "chrome://settings/appearance",
        },
        "vscode": {
            "markdown": "# Enable Dark Mode in VSCode\n\n1. Open Color Theme\n2. Select 'Dark Modern'",
            "steps": [
                {"step": 1, "target": "Color Theme", "action": "click", "instruction": "Open Color Theme in VSCode."},
                {"step": 2, "target": "Dark", "action": "click", "instruction": "Select 'Dark Modern' theme."},
            ],
        },
        "windows": {
            "markdown": (
                "# Enable Dark Mode in Windows\n\n"
                "1. Open Settings (press Win+I or click Start -> Settings)\n"
                "2. Click on 'Personalization'\n"
                "3. Click on 'Colors'\n"
                "4. Select 'Dark' from the 'Choose your mode' dropdown"
            ),
            "steps": [
                {"step": 1, "target": "Personalization", "action": "click", "instruction": "Click 'Personalization' in Settings."},
                {"step": 2, "target": "Colors", "action": "click", "instruction": "Click 'Colors' under Personalization."},
                {"step": 3, "target": "Choose your mode", "action": "click", "instruction": "Click 'Choose your mode' dropdown."},
                {"step": 4, "target": "Dark", "action": "click", "instruction": "Select 'Dark' theme mode."},
            ],
            "app_to_open": "ms-settings:colors",
        },
        "linux": {
            "markdown": (
                "# Enable Dark Mode on Linux / GNOME\n\n"
                "1. Open Settings\n"
                "2. Click on 'Appearance'\n"
                "3. Select 'Dark' style"
            ),
            "steps": [
                {"step": 1, "target": "Appearance", "action": "click", "instruction": "Click 'Appearance' in Settings."},
                {"step": 2, "target": "Dark", "action": "click", "instruction": "Select 'Dark' style."},
            ],
            "app_to_open": "gnome-control-center appearance",
        },
    },
    "light_mode": {
        "patterns": [r"light\s*mode", r"light\s*theme", r"switch\s*to\s*light", r"enable\s*light"],
        "msedge": {
            "markdown": "# Enable Light Mode in Microsoft Edge\n\n1. Open Edge Settings\n2. Click Appearance\n3. Select 'Light' theme",
            "steps": [
                {"step": 1, "target": "Appearance", "action": "click", "instruction": "Click 'Appearance' in Edge Settings."},
                {"step": 2, "target": "Light", "action": "click", "instruction": "Select 'Light' overall appearance theme in Edge."},
            ],
            "app_to_open": "edge://settings/appearance",
        },
        "chrome": {
            "markdown": "# Enable Light Mode in Google Chrome\n\n1. Open Chrome Settings\n2. Click Appearance\n3. Select 'Light' mode",
            "steps": [
                {"step": 1, "target": "Appearance", "action": "click", "instruction": "Click 'Appearance' in Chrome Settings."},
                {"step": 2, "target": "Light", "action": "click", "instruction": "Select 'Light' theme in Chrome."},
            ],
            "app_to_open": "chrome://settings/appearance",
        },
        "vscode": {
            "markdown": "# Enable Light Mode in VSCode\n\n1. Open Color Theme\n2. Select 'Light Modern'",
            "steps": [
                {"step": 1, "target": "Color Theme", "action": "click", "instruction": "Open Color Theme in VSCode."},
                {"step": 2, "target": "Light", "action": "click", "instruction": "Select 'Light Modern' theme."},
            ],
        },
        "windows": {
            "markdown": (
                "# Enable Light Mode in Windows\n\n"
                "1. Open Settings\n"
                "2. Click on 'Personalization'\n"
                "3. Click on 'Colors'\n"
                "4. Select 'Light' from the 'Choose your mode' dropdown"
            ),
            "steps": [
                {"step": 1, "target": "Personalization", "action": "click", "instruction": "Click 'Personalization' in Settings."},
                {"step": 2, "target": "Colors", "action": "click", "instruction": "Click 'Colors' under Personalization."},
                {"step": 3, "target": "Choose your mode", "action": "click", "instruction": "Click 'Choose your mode' dropdown."},
                {"step": 4, "target": "Light", "action": "click", "instruction": "Select 'Light' theme mode."},
            ],
            "app_to_open": "ms-settings:colors",
        },
        "linux": {
            "markdown": (
                "# Enable Light Mode on Linux / GNOME\n\n"
                "1. Open Settings\n"
                "2. Click on 'Appearance'\n"
                "3. Select 'Light' style"
            ),
            "steps": [
                {"step": 1, "target": "Appearance", "action": "click", "instruction": "Click 'Appearance' in Settings."},
                {"step": 2, "target": "Default", "action": "click", "instruction": "Select 'Default' or 'Light' style."},
            ],
            "app_to_open": "gnome-control-center appearance",
        },
    },
}


def _run_async_in_thread(coro: Any) -> Any:
    future: Future[Any] = Future()

    def run_in_thread() -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
            future.set_result(result)
        except Exception as ex:
            future.set_exception(ex)
        finally:
            loop.close()

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    return future.result()


async def search_searxng_for_procedure(query: str, app_title: str = "", os_type: str = "Windows") -> str:
    """Query SearXNG for procedural step-by-step guides."""
    from wil.searxng_client import SearXNGClient

    search_query = f"{app_title or os_type} how to {query} step by step tutorial"
    try:
        client = SearXNGClient()
        results = await client.search_category(search_query, category="general", limit=4)
        snippets: list[str] = []
        for r in results:
            title = r.get("title", "")
            content = r.get("content", "")
            if content:
                snippets.append(f"Title: {title}\nInstructions: {content}")
        return "\n\n".join(snippets)
    except Exception as exc:
        LOGGER.warning("SearXNG procedural search failed for '%s': %s", search_query, exc)
        return ""


def check_builtin_template(
    query: str,
    os_type: str = "windows",
    active_app: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Check if the query matches a known high-frequency operating system or application workflow."""
    q_lower = query.lower().strip()
    proc = str(active_app.get("process", "")).lower() if active_app else ""
    title = str(active_app.get("title", "")).lower() if active_app else ""

    app_key = None
    if "msedge" in proc or "edge" in title:
        app_key = "msedge"
    elif "chrome" in proc or "chrome" in title:
        app_key = "chrome"
    elif "code" in proc or "visual studio code" in title:
        app_key = "vscode"

    for template_name, template_data in _COMMON_PROCEDURAL_TEMPLATES.items():
        patterns = template_data.get("patterns", [])
        if any(re.search(p, q_lower) for p in patterns):
            matched_plan = None
            if app_key and app_key in template_data:
                matched_plan = template_data[app_key]
            else:
                os_key = "linux" if "linux" in os_type.lower() else "windows"
                matched_plan = template_data.get(os_key) or template_data.get("windows")

            if matched_plan:
                LOGGER.info("Matched built-in procedural template for '%s' (app=%s)", template_name, app_key or os_type)
                return {
                    "task": query,
                    "markdown_guide": matched_plan["markdown"],
                    "steps": matched_plan["steps"],
                    "app_to_open": matched_plan.get("app_to_open"),
                    "summary": f"Here is the step-by-step procedure to {query}.",
                    "source": "builtin_template",
                }
    return None


def generate_procedural_plan(
    query: str,
    active_app: dict[str, Any] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Generate a concise markdown procedural plan and structured steps array
    using SearXNG search context and Groq text model (ask_text_model).
    """
    os_type = "Linux" if platform.system() == "Linux" else "Windows"
    app_title = ""
    app_process = ""
    if active_app:
        app_title = str(active_app.get("title", "")).strip()
        app_process = str(active_app.get("process", "")).strip()

    # 1. Quick check for common built-in OS or application templates (dark mode, light mode, etc.)
    builtin = check_builtin_template(query, os_type=os_type, active_app=active_app)
    if builtin:
        return builtin

    # 2. Query SearXNG for web documentation and step-by-step tutorials
    search_context = ""
    try:
        search_context = _run_async_in_thread(
            search_searxng_for_procedure(query, app_title=app_title or app_process, os_type=os_type)
        )
    except Exception as exc:
        LOGGER.warning("SearXNG async search failed: %s", exc)

    # 3. Prompt Groq Text Model to build a clean procedural plan
    prompt = f"""You are Blinky, an expert desktop automation planner running on {os_type}.
The user wants to accomplish the following task on their computer:
Task: "{query}"

Current active app: {app_title or app_process or "Desktop"}
OS: {os_type}

Reference documentation & search results:
{search_context if search_context else "No external search results found. Use your expert operating system knowledge."}

Your job:
1. Break this task down into the minimum required sequential steps.
2. Formulate a clean, formatted Markdown step-by-step guide.
3. Extract an array of actionable atomic UI steps. Each step must define:
   - "step": integer index (1-based)
   - "target": concise name of the button, tab, menu, dropdown item, or input to click/interact with
   - "action": "click", "type", "press_key", "open_app", or "shortcut"
   - "text_to_type": text string if action is "type", else ""
   - "key": key string if action is "press_key" (e.g. "Enter", "Win+I"), else ""
   - "instruction": clear, user-facing instruction (e.g. "Click 'Personalization' in the left menu")

Output ONLY valid JSON matching this schema:
{{
  "task": "{query}",
  "markdown_guide": "# Steps to ...\\n1. ...\\n2. ...",
  "summary": "Concise summary of the workflow",
  "steps": [
    {{
      "step": 1,
      "target": "Settings",
      "action": "click",
      "text_to_type": "",
      "key": "",
      "instruction": "Open Windows Settings"
    }}
  ]
}}
"""

    try:
        response = ask_text_model(prompt, max_tokens=1024)
        if isinstance(response, dict) and response.get("steps"):
            steps = response.get("steps", [])
            normalized_steps = []
            for i, s in enumerate(steps, start=1):
                if isinstance(s, dict):
                    normalized_steps.append({
                        "step": s.get("step") or i,
                        "target": str(s.get("target", "")).strip(),
                        "action": str(s.get("action", "click")).lower().strip(),
                        "text_to_type": str(s.get("text_to_type", "")).strip(),
                        "key": str(s.get("key", "")).strip(),
                        "instruction": str(s.get("instruction", "")).strip() or f"Click {s.get('target', 'item')}",
                    })
                elif isinstance(s, str) and s.strip():
                    normalized_steps.append({
                        "step": i,
                        "target": s.strip(),
                        "action": "click",
                        "text_to_type": "",
                        "key": "",
                        "instruction": f"Click {s.strip()}",
                    })

            return {
                "task": query,
                "markdown_guide": str(response.get("markdown_guide", "")).strip(),
                "summary": str(response.get("summary", "")).strip() or f"Step-by-step guide for {query}",
                "steps": normalized_steps,
                "source": "searxng_text_llm",
            }
    except Exception as exc:
        LOGGER.error("Failed to generate procedural plan via LLM: %s", exc)

    # 4. Graceful Fallback if LLM or search fails
    return {
        "task": query,
        "markdown_guide": f"# {query}\n\n1. Identify the target control on screen.\n2. Click or type to proceed.",
        "summary": f"Follow the on-screen steps for {query}.",
        "steps": [
            {
                "step": 1,
                "target": query,
                "action": "click",
                "text_to_type": "",
                "key": "",
                "instruction": f"Click or navigate to {query}",
            }
        ],
        "source": "fallback",
    }
