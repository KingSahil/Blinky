"""Resolve a mobile attachment's destination using Blinky's configured text AI.

The model may only select a folder discovered on the PC. File writing remains
in the authenticated Rust transfer server after its usual path checks.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from ai.client import ask_text_model


def discover_folders(roots: list[Path], limit: int = 1500) -> list[str]:
    folders: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for current, subdirs, _ in os.walk(root, followlinks=False):
            depth = len(Path(current).relative_to(root).parts)
            subdirs[:] = sorted(
                name for name in subdirs
                if not name.startswith(".") and name.lower() not in {
                    "node_modules", "appdata", "$recycle.bin", "system volume information"
                }
            ) if depth < 4 else []
            canonical = str(Path(current).resolve())
            key = os.path.normcase(canonical)
            if key not in seen:
                folders.append(canonical)
                seen.add(key)
            if len(folders) >= limit:
                return folders
    return folders


def drive_folders(instruction: str) -> list[str]:
    """List direct children of the system drive and any drive named in chat."""
    letters = set(re.findall(r"\b([A-Za-z])\s*:?[ \t]*drive\b", instruction, flags=re.I))
    system_drive = os.environ.get("SystemDrive", "")
    if re.fullmatch(r"[A-Za-z]:", system_drive):
        letters.add(system_drive[0])
    folders: list[str] = []
    for letter in sorted(letters):
        try:
            with os.scandir(f"{letter.upper()}:\\") as entries:
                folders.extend(entry.path for entry in entries if entry.is_dir(follow_symlinks=False))
        except (OSError, PermissionError):
            continue
    return sorted(folders, key=str.casefold)[:150]


def folder_label(folder: str) -> str:
    """Give the model a useful label while keeping the profile path local."""
    path = Path(folder)
    try:
        return "Home/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return path.as_posix()


def choose_destination_decision(instruction: str, folders: list[str]) -> tuple[str | None, bool]:
    words = set(re.findall(r"[a-z0-9]+", instruction.lower())) - {
        "a", "all", "and", "can", "copy", "file", "files", "folder", "for", "i",
        "in", "into", "it", "keep", "me", "my", "on", "pc", "please", "put",
        "save", "send", "the", "these", "this", "to", "where",
    }
    if len(folders) > 120:
        scored = []
        for index, folder in enumerate(folders):
            name = Path(folder).name.lower()
            path_words = set(re.findall(r"[a-z0-9]+", folder.lower()))
            score = sum(5 if word in name else 1 for word in words if word in path_words)
            scored.append((score, index, folder))
        best = sorted(scored, key=lambda item: (-item[0], item[1]))[:110]
        folders = list(dict.fromkeys(folders[:10] + [folder for _, _, folder in best]))[:120]
    listed = "\n".join(f"{index}: {folder_label(folder)}" for index, folder in enumerate(folders))
    prompt = (
        "You are choosing where files sent from a phone should be stored on this PC. "
        "Read the user's full instruction. Return JSON only: "
        "{\"folder_id\": number|null, \"folder_requested\": boolean}. "
        "Choose the best matching folder from the numbered list. "
        "When the user says a folder is in a named drive, prefer a direct child of that drive. "
        "Return null if the user gives no folder, if the requested folder is absent, "
        "or if the destination is ambiguous. Never invent a path or folder.\n"
        f"USER INSTRUCTION: {json.dumps(instruction)}\n"
        f"EXISTING PC FOLDERS:\n{listed}"
    )
    result = ask_text_model(prompt, max_tokens=80)
    folder_id = result.get("folder_id") if isinstance(result, dict) else None
    requested = result.get("folder_requested") is not False if isinstance(result, dict) else True
    if isinstance(folder_id, bool) or not isinstance(folder_id, int):
        return None, requested
    if not 0 <= folder_id < len(folders):
        return None, requested
    return folders[folder_id], requested


def choose_destination(instruction: str, folders: list[str]) -> str | None:
    return choose_destination_decision(instruction, folders)[0]


def _roots(payload: dict) -> list[Path]:
    roots = [Path(item) for item in payload.get("roots", []) if isinstance(item, str) and item]
    instruction = str(payload.get("instruction", ""))
    # Include a full path supplied in chat even when it lies outside the usual
    # profile folders. The Rust receiver still checks existence and writability.
    for match in re.finditer(r"(?:[A-Za-z]:[\\/]|\\\\)[^\n,;\"']+", instruction):
        candidate = re.split(r"\s+(?:and|folder|directory)\b", match.group().strip(), 1, flags=re.I)[0].rstrip(" .")
        path = Path(candidate)
        if path.is_dir():
            roots.insert(0, path)
    return roots


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        instruction = str(payload.get("instruction", "")).strip()
        if not instruction:
            print(json.dumps({"path": None, "reason": "no_prompt"}))
            return
        folders = list(dict.fromkeys(drive_folders(instruction) + discover_folders(_roots(payload))))
        path, requested = choose_destination_decision(instruction, folders)
        reason = None if path else ("not_found" if requested else "no_folder_requested")
        print(json.dumps({"path": path, "reason": reason}))
    except Exception as error:
        print(json.dumps({"path": None, "reason": "ai_unavailable", "detail": str(error)}))


if __name__ == "__main__":
    main()
