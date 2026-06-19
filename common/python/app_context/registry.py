from __future__ import annotations

import asyncio
import re
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from utils.logging import get_logger

LOGGER = get_logger("blinky.app_context")

APP_CONTEXT_DIR = Path(__file__).resolve().parent

APP_CONTEXT_FILES = {
    "code": "vscode.md",
    "code.exe": "vscode.md",
    "chrome": "browser.md",
    "chrome.exe": "browser.md",
    "msedge": "browser.md",
    "msedge.exe": "browser.md",
    "explorer": "file_explorer.md",
    "explorer.exe": "file_explorer.md",
    "spotify": "windows_apps.md",
    "spotify.exe": "windows_apps.md",
    "systemsettings": "systemsettings.md",
    "systemsettings.exe": "systemsettings.md",
}


def run_async(coro):
    future = Future()

    def run_in_thread():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
            future.set_result(result)
        except Exception as ex:
            future.set_exception(ex)
        finally:
            loop.close()

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    return future.result()


async def search_searxng_for_app(query: str) -> str:
    from wil.searxng_client import SearXNGClient
    try:
        client = SearXNGClient()
        results = await client.search_category(query, category="general", limit=5)
        snippets = []
        for r in results:
            title = r.get("title", "")
            content = r.get("content", "")
            snippets.append(f"Title: {title}\nSnippet: {content}")
        return "\n\n".join(snippets)
    except Exception as e:
        LOGGER.warning(f"SearXNG app context search failed: {e}")
        return ""


def generate_context_file(process_name: str, app_title: str, filepath: Path) -> bool:
    # 1. Search for guides on SearXNG
    search_query = f"{app_title or process_name} Windows app keyboard shortcuts menus navigation help support"
    search_results = ""
    try:
        search_results = run_async(search_searxng_for_app(search_query))
    except Exception as e:
        LOGGER.warning(f"Failed running SearXNG search: {e}")

    prompt = f"""You are Blinky, an expert Windows desktop assistant tutor.
We need to generate a markdown context navigation guide for a new application.
Process Name: {process_name}
Window Title: {app_title}

Search results about this app's menus, behavior, and guides:
{search_results}

Create a concise and clear markdown guide for Blinky to understand how to navigate this app.
In your guide:
1. Describe the app's standard behaviors.
2. Outline known navigation paths (e.g. how to open Settings, how to access Help/Support, common menus, or shortcuts).
3. Keep the content brief and structured using headers and bullet points.

You MUST return your response as a JSON object with a single key "context" containing the markdown text as its string value.
Example format:
{{"context": "# App Name\\n\\nKnown behaviors:\\n- Shortcut: Ctrl+S to save\\n- Help: Click profile icon, then help."}}
"""
    try:
        from ai.client import ask_text_model
        response = ask_text_model(prompt, max_tokens=600)
        markdown_content = response.get("context", "").strip()
        if markdown_content:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(markdown_content, encoding="utf-8")
            LOGGER.info(f"Dynamically generated app context saved to {filepath}")
            return True
    except Exception as e:
        LOGGER.error(f"Failed to generate context dynamically via LLM: {e}")

    # Fallback Boilerplate if LLM / Search fails
    clean_title = app_title if app_title else process_name.rsplit(".", 1)[0].capitalize()
    boilerplate = f"""# {clean_title}

Known behavior:
- This is a Windows application: {process_name}.
- Standard shortcuts: F1 for Help, Ctrl+, for Settings.
"""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(boilerplate, encoding="utf-8")
        LOGGER.info(f"Saved fallback boilerplate context to {filepath}")
        return True
    except Exception as exc:
        LOGGER.error(f"Failed to save fallback boilerplate to {filepath}: {exc}")
        return False


def get_app_context(active_app: dict | None) -> str:
    if not isinstance(active_app, dict):
        return ""

    process = str(active_app.get("process", "")).strip().lower()
    title = str(active_app.get("title", "")).strip().lower()
    
    if not process or process == "idle":
        return ""

    context_files: list[str] = []

    filename = APP_CONTEXT_FILES.get(process) or APP_CONTEXT_FILES.get(process.rsplit(".", 1)[0])
    if not filename:
        # Check if a custom context file already exists on disk
        clean_name = process.rsplit(".", 1)[0]
        potential_filename = f"{clean_name}.md"
        potential_path = APP_CONTEXT_DIR / potential_filename
        
        if potential_path.exists():
            APP_CONTEXT_FILES[process] = potential_filename
            filename = potential_filename
        else:
            # Generate it dynamically
            success = generate_context_file(process, title, potential_path)
            if success:
                APP_CONTEXT_FILES[process] = potential_filename
                filename = potential_filename

    if filename:
        context_files.append(filename)

    if "visual studio code" in title or process.startswith("code"):
        context_files.append("vscode.md")
    if "edge" in title or "chrome" in title:
        context_files.append("browser.md")
    if process in {"explorer.exe", "explorer"}:
        context_files.append("file_explorer.md")

    context_files.append("windows_apps.md")

    chunks: list[str] = []
    seen: set[str] = set()
    for name in context_files:
        if name in seen:
            continue
        seen.add(name)
        path = APP_CONTEXT_DIR / name
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8").strip())

    return "\n\n".join(chunk for chunk in chunks if chunk)
