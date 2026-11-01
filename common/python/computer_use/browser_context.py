"""Short-lived routing context shared by per-request PC and mobile workers."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTEXT = ROOT / "data/agent-tools/last-browser-target.json"
TASK_CONTEXT = ROOT / "data/agent-tools/browser-task.json"


def save_browser_task(task: str, history: list[dict], state: str) -> None:
    TASK_CONTEXT.parent.mkdir(parents=True, exist_ok=True)
    TASK_CONTEXT.write_text(json.dumps({"task": task, "history": history, "state": state,
                                       "updated": time.time()}, ensure_ascii=False), encoding="utf-8")


def browser_continuation(query: str) -> dict | None:
    if not re.fullmatch(r"\s*(?:please\s+)?(?:continue|keep\s+going|carry\s+on|resume|finish(?:\s+it)?)[.!?]*\s*", query, re.I):
        return None
    if not recent_browser_context():
        return None
    try:
        saved = json.loads(TASK_CONTEXT.read_text(encoding="utf-8"))
        if (saved.get("state") in {"failed", "blocked"} and saved.get("task")
                and 0 <= time.time() - float(saved["updated"]) < 600):
            return saved
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def remember_browser(url: str = "") -> None:
    CONTEXT.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT.write_text(json.dumps({"url": url, "updated": time.time()}), encoding="utf-8")


def recent_browser_context() -> bool:
    """Routing hint only; the browser adapter still observes live refs before acting."""
    desktop = ROOT / "data/agent-tools/last-desktop-target.json"
    try:
        target = json.loads(desktop.read_text(encoding="utf-8"))
        browser = target.get("app_name", "").lower() in {"msedge.exe", "chrome.exe", "brave.exe", "firefox.exe"}
        if time.time() - desktop.stat().st_mtime < 600:
            if browser:
                return True
            if not CONTEXT.exists() or desktop.stat().st_mtime > CONTEXT.stat().st_mtime:
                return False
    except (OSError, ValueError):
        pass
    try:
        saved = json.loads(CONTEXT.read_text(encoding="utf-8"))
        return 0 <= time.time() - float(saved["updated"]) < 600
    except (OSError, ValueError, KeyError, TypeError):
        return False
