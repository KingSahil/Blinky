"""
Windows File Explorer context inspector for Blinky.
Extracts active directory path, selected files, and media files from open File Explorer windows.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

MEDIA_EXTENSIONS = {
    "video": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v"},
    "audio": {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg", ".wma"},
}


def get_active_explorer_context() -> dict[str, Any]:
    """
    Query open File Explorer windows on Windows via COM Shell.Application.
    Returns:
      active_directory: path of active or first explorer folder
      selected_files: list of paths for currently selected items
      selected_videos: list of paths for selected video files
      selected_audios: list of paths for selected audio files
      media_files_in_folder: all video and audio files in active folder
      open_windows: list of open explorer window info dicts
    """
    context: dict[str, Any] = {
        "active_directory": None,
        "selected_files": [],
        "selected_videos": [],
        "selected_audios": [],
        "media_files_in_folder": [],
        "open_windows": [],
    }

    if sys.platform != "win32":
        return context

    try:
        import win32com.client

        shell = win32com.client.Dispatch("Shell.Application")
        windows = shell.Windows()

        for w in windows:
            full_name = getattr(w, "FullName", "").lower()
            if "explorer" not in full_name:
                continue

            try:
                doc = w.Document
                folder = doc.Folder
                folder_path = folder.Self.Path
                if not folder_path:
                    continue

                win_info: dict[str, Any] = {
                    "title": getattr(w, "LocationName", ""),
                    "path": folder_path,
                    "selected": [],
                }

                selected = doc.SelectedItems()
                for i in range(selected.Count):
                    item_path = selected.Item(i).Path
                    win_info["selected"].append(item_path)

                context["open_windows"].append(win_info)

                # Prioritize windows that have selected files
                if context["active_directory"] is None or (win_info["selected"] and not context["selected_files"]):
                    context["active_directory"] = folder_path
                    context["selected_files"] = win_info["selected"]
            except Exception:
                continue

        # Categorize selected files
        for f in context["selected_files"]:
            ext = Path(f).suffix.lower()
            if ext in MEDIA_EXTENSIONS["video"]:
                context["selected_videos"].append(f)
            elif ext in MEDIA_EXTENSIONS["audio"]:
                context["selected_audios"].append(f)

        # List all media files in active directory
        if context["active_directory"] and os.path.isdir(context["active_directory"]):
            act_dir = Path(context["active_directory"])
            try:
                for entry in act_dir.iterdir():
                    if entry.is_file():
                        ext = entry.suffix.lower()
                        if ext in MEDIA_EXTENSIONS["video"] or ext in MEDIA_EXTENSIONS["audio"]:
                            context["media_files_in_folder"].append(str(entry.resolve()))
            except Exception:
                pass

    except Exception as exc:
        context["error"] = str(exc)

    return context
