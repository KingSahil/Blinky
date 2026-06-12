from __future__ import annotations

from pathlib import Path


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
}


def get_app_context(active_app: dict | None) -> str:
    if not isinstance(active_app, dict):
        return ""

    process = str(active_app.get("process", "")).strip().lower()
    title = str(active_app.get("title", "")).strip().lower()
    context_files: list[str] = []

    filename = APP_CONTEXT_FILES.get(process) or APP_CONTEXT_FILES.get(process.rsplit(".", 1)[0])
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
