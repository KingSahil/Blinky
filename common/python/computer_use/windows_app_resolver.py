"""Resolve Windows display names to installed executables or registered app IDs.

This module only discovers applications. UI actions stay with agent-desktop.
It never types application names into Windows Search or executes model code.
"""
from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

DISPLAY_NAMES = {
    "code": "Visual Studio Code", "vscode": "Visual Studio Code", "vscodeexe": "Visual Studio Code",
    "visualstudiocode": "Visual Studio Code",
    "vlc": "VLC media player", "vlcmedia": "VLC media player", "vlcmediaplayer": "VLC media player",
    "spotify": "Spotify", "whatsapp": "WhatsApp", "whatsappdesktop": "WhatsApp",
    "calc": "Calculator", "calculator": "Calculator", "mspaint": "Paint",
    "store": "Microsoft Store", "microsoftstore": "Microsoft Store",
}
PROCESS_NAMES = {
    "visualstudiocode": ["code.exe"], "vlcmediaplayer": ["vlc.exe"],
    "spotify": ["spotify.exe"], "whatsapp": ["whatsapp.root.exe", "whatsapp.exe"],
    "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
    "paint": ["mspaint.exe", "paintapp.exe"], "settings": ["systemsettings.exe"],
}


def normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().removesuffix(".exe"))


def display_name(name: str) -> str:
    return DISPLAY_NAMES.get(normalized(name), name.removesuffix(".exe").strip())


def matching_windows(windows: list[dict], name: str, target: dict | None = None) -> list[dict]:
    display = (target or {}).get("name", display_name(name))
    processes = set(PROCESS_NAMES.get(normalized(display), []))
    processes.add(name.lower() if name.lower().endswith(".exe") else name.lower() + ".exe")
    if target and target.get("kind") == "executable":
        processes.add(Path(target["target"]).name.lower())
    matches = []
    for window in windows:
        process, title = window.get("app_name", "").lower(), window.get("title", "").lower()
        titled = title == display.lower() or title.endswith(" - " + display.lower())
        if process in processes or titled:
            matches.append(window)
    return matches


@lru_cache(maxsize=1)
def registered_apps() -> list[dict]:
    script = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or not result.stdout.strip():
        return []
    payload = json.loads(result.stdout.lstrip("\ufeff"))
    return payload if isinstance(payload, list) else [payload]


def _registered_executable(executable: str) -> str | None:
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}",
                                    0, winreg.KEY_READ | view) as key:
                    raw = os.path.expandvars(str(winreg.QueryValue(key, None))).strip().strip('"')
                    if Path(raw).is_file():
                        return raw
            except OSError:
                continue
    return None


def resolve_application(name: str) -> dict:
    display = display_name(name)
    key = normalized(display)
    process_names = PROCESS_NAMES.get(key, [name if name.lower().endswith(".exe") else name + ".exe"])
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    program_files = [Path(os.environ.get("ProgramFiles", "C:/Program Files")),
                     Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))]
    known = {
        "visualstudiocode": [local / "Programs/Microsoft VS Code/Code.exe"] + [p / "Microsoft VS Code/Code.exe" for p in program_files],
        "spotify": [roaming / "Spotify/Spotify.exe", local / "Spotify/Spotify.exe"],
        "vlcmediaplayer": [p / "VideoLAN/VLC/vlc.exe" for p in program_files],
        "notepad": [Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/notepad.exe"],
    }
    for executable in process_names:
        candidate = _registered_executable(executable)
        if candidate:
            return {"kind": "executable", "target": candidate, "name": display}
    for candidate in known.get(key, []):
        if candidate.is_file():
            return {"kind": "executable", "target": str(candidate), "name": display}
    for executable in process_names:
        candidate = shutil.which(executable)
        if candidate and Path(candidate).suffix.lower() == ".exe":
            return {"kind": "executable", "target": candidate, "name": display}
    try:
        entries = registered_apps()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        entries = []
    matches = [entry for entry in entries if normalized(str(entry.get("Name", ""))) == key]
    if not matches:
        # Permit an unambiguous prefix, never a fuzzy match against another app.
        matches = [entry for entry in entries if normalized(str(entry.get("Name", ""))).startswith(key)]
    if len(matches) == 1 and matches[0].get("AppID"):
        entry = matches[0]
        identifier = str(entry["AppID"])
        if Path(identifier).is_file() and Path(identifier).suffix.lower() == ".exe":
            return {"kind": "executable", "target": identifier, "name": entry["Name"]}
        return {"kind": "app_id", "target": identifier, "name": entry["Name"]}
    if len(matches) > 1:
        names = ", ".join(str(entry["Name"]) for entry in matches[:5])
        raise RuntimeError(f"Several installed apps match '{name}': {names}. Use the full app name.")
    raise RuntimeError(f"Windows could not resolve an installed app named '{name}'. Use its Start menu name.")
